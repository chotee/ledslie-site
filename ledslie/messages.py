import base64
import json

import binascii
from twisted.logger import Logger

from ledslie.config import Config
from ledslie.definitions import ALERT_PRIO_STRING

log = Logger()


def SerializeFrame(frame: bytes) -> str:
    return base64.encodebytes(frame).decode('ascii')


def DeserializeFrame(encoded_frame: str) -> bytes:
    return base64.decodebytes(encoded_frame.encode('ascii'))


class GenericMessage(object):
    def load(self, obj_data):
        raise NotImplemented()

    def __bytes__(self):
        raise NotImplemented("Deprecated")

    def serialize(self):
        return bytearray(json.dumps(self.__dict__), 'utf-8')


class GenericProgram(GenericMessage):
    def __init__(self):
        self.program = None
        self.valid_time = None

    def load(self, prog_data):
        self.program = prog_data.get('program', None)
        self.valid_time = prog_data.get('valid_time', None)


class Frame(GenericMessage):
    def __init__(self, img_data, duration):
        self.img_data = img_data
        self.duration = duration

    def serialize(self):
        return SerializeFrame(self.img_data), {'duration': self.duration}

    def raw(self):
        return self.img_data


class FrameSequence(GenericProgram):
    def __init__(self):
        super().__init__()
        self._config = Config()
        self.frames = []
        self.prio = None
        self.frame_nr = -1

    def load(self, payload: bytearray):
        seq_images, seq_info = json.loads(payload.decode())
        super().load(seq_info)
        self.prio = seq_info.get('prio', None)
        for image_data_encoded, image_info in seq_images:
            try:
                image_data = DeserializeFrame(image_data_encoded)
            except binascii.Error:
                return
            if len(image_data) != self._config.get('DISPLAY_SIZE'):
                log.error("Frame is of the wrong length %d, expected %d. Ignoring." % (
                    len(image_data), self._config.get('DISPLAY_SIZE')))
                return
            try:
                image_duration = image_info.get('duration', self._config['DISPLAY_DEFAULT_DELAY'])
            except KeyError:
                break
            self.frames.append(Frame(image_data, duration=image_duration))
        return self

    def serialize(self):
        images = []
        for frame in self.frames:
            if hasattr(frame, 'serialize'):
                images.append(frame.serialize())
            else:
                idata, iinfo = frame
                images.append((SerializeFrame(idata), iinfo))
        sequence_info = {}
        if self.prio is not None:
            sequence_info['prio'] = self.prio
        return bytearray(json.dumps((images, sequence_info)), 'utf-8')

    @property
    def duration(self):
        return sum([i.duration for i in self.frames])

    def next_frame(self):
        self.frame_nr += 1
        try:
            return self.frames[self.frame_nr]
        except IndexError:
            self.frame_nr = -1
            raise

    def is_alert(self):
        return self.prio == ALERT_PRIO_STRING

    def add_frame(self, frame: Frame):
        self.frames.append(frame)

    def is_empty(self):
        return len(self) == 0

    def __len__(self):
        return len(self.frames)

    def __getitem__(self, nr):
        return self.frames[nr]


class GenericTextLayout(GenericProgram):
    def __init__(self):
        super().__init__()
        self.duration = None

    def load(self, payload):
        obj_data = json.loads(payload.decode())
        super().load(obj_data)
        self.duration = obj_data.get('duration', None)
        return obj_data


class TextSingleLineLayout(GenericTextLayout):
    def __init__(self):
        super().__init__()
        self.text = ""
        self.font_size = None

    def load(self, payload):
        obj_data = super(TextSingleLineLayout, self).load(payload)
        self.text = obj_data.get('text', "")
        self.font_size = obj_data.get('font_size', None)
        return self


class TextTripleLinesLayout(GenericTextLayout):
    def __init__(self):
        super().__init__()
        self.lines = []

    def load(self, payload):
        obj_data = super(TextTripleLinesLayout, self).load(payload)
        self.lines = obj_data.get('lines', [])
        return self


class TextAlertLayout(GenericTextLayout):
    def __init__(self):
        super().__init__()
        self.text = ""
        self.who = ""

    def load(self, payload):
        obj_data = super(TextAlertLayout, self).load(payload)
        self.text = obj_data.get('text', "")
        self.who = obj_data.get('who', "")
        return self
