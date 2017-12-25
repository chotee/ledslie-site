import pytest

import json

import ledslie.processors.scheduler
from ledslie.config import Config
from ledslie.definitions import LEDSLIE_TOPIC_SEQUENCES_UNNAMED, LEDSLIE_TOPIC_SEQUENCES_PROGRAMS
from ledslie.messages import FrameSequence, SerializeFrame, Frame
from ledslie.processors.scheduler import Scheduler
from ledslie.tests.fakes import FakeMqttProtocol, FakeLogger
from ledslie.processors.scheduler import Catalog
from ledslie.processors.animate import AnimateStill


class TestCatalog(object):
    def test_init(self, catalog=None):
        catalog = Catalog() if catalog is None else catalog
        assert catalog.is_empty()
        assert not catalog.has_content()

        self._create_and_add_sequence(catalog, "First", ["Foo"])

        assert not catalog.is_empty()
        assert catalog.has_content()

        self._create_and_add_sequence(catalog, "Second", ["Bar", "Quux"])

        return catalog

    def _create_and_add_sequence(self, catalog, program_id, sequence_content):
        seq = FrameSequence()
        seq.program = program_id
        seq.frames = sequence_content
        catalog.add_program(program_id, seq)

    def test_get_frames(self):
        catalog = self.test_init()
        assert "Foo" == catalog.next_frame()
        assert "Bar" == catalog.next_frame()
        assert "Quux" == catalog.next_frame()
        assert "Foo" == catalog.next_frame()

    def test_empty_catalog(self):
        catalog = Catalog()
        try:
            catalog.next_frame()
        except IndexError:
            pass
        else:
            assert "Should not get here!"

    def test_remove_program(self):
        catalog = self.test_init()
        assert catalog.has_content()
        catalog.remove_program("First")
        catalog.remove_program("Second")
        try: catalog.remove_program("Missing")
        except KeyError: pass
        else: assert False

    def test_program_retire(self):
        catalog = Catalog()
        catalog.now = lambda: 10
        self._create_and_add_sequence(catalog, "First", ["Foo"])
        assert "Foo" == catalog.next_frame()  # Only foo is shown
        assert "Foo" == catalog.next_frame()
        catalog.now = lambda: 20  # Time passes
        self._create_and_add_sequence(catalog, "Second", ["Bar"])
        assert "Bar" == catalog.next_frame()
        assert "Foo" == catalog.next_frame()
        assert "Bar" == catalog.next_frame()
        catalog.now = lambda: 20+Config()["PROGRAM_RETIREMENT_AGE"]
        assert "Foo" == catalog.next_frame()  # Foo now gets retired.
        assert "Bar" == catalog.next_frame()
        assert "Bar" == catalog.next_frame()
        self._create_and_add_sequence(catalog, "Second", ["Bar2"])  # "Second" got updated
        assert "Bar2" == catalog.next_frame()
        catalog.now = lambda: 30+Config()["PROGRAM_RETIREMENT_AGE"]
        assert "Bar2" == catalog.next_frame()  # Still exists, because "Second" was updated.


class TestScheduler(object):

    @pytest.fixture
    def sched(self):
        endpoint = None
        factory = None
        s = Scheduler(endpoint, factory)
        s.protocol = FakeMqttProtocol()
        return s

    def test_on_connect(self, sched):
        ledslie.processors.scheduler.log = FakeLogger()
        protocol = FakeMqttProtocol()
        sched.connectToBroker(protocol)

    def test_on_message(self, sched):
        topic = LEDSLIE_TOPIC_SEQUENCES_PROGRAMS[:-1] + "test"
        payload = self._test_sequence(sched)
        assert sched.catalog.is_empty()
        sched.onPublish(topic, payload, qos=0, dup=False, retain=False, msgId=0)
        assert not sched.catalog.is_empty()

    def _test_sequence(self, sched):
        sequence_info = {}
        image_size = sched.config.get('DISPLAY_SIZE')
        image_sequence = [
            [SerializeFrame(b'0' * image_size), {'duration': 100}],
            [SerializeFrame(b'1' * image_size), {'duration': 100}],
            [SerializeFrame(b'2' * image_size), {'duration': 100}],
        ]
        payload = json.dumps([image_sequence, sequence_info])
        return payload.encode()

    def test_send_next_frame(self, sched):
        image_size = sched.config.get('DISPLAY_SIZE')
        sched.catalog.add_program(None, FrameSequence().load(self._test_sequence(sched)))
        assert 0 == len(sched.protocol._published_messages)

        sched.send_next_frame()  # Frame 0
        assert 1 == len(sched.protocol._published_messages)
        assert 'ledslie/frames/1' == sched.protocol._published_messages[-1][0]
        assert b'0' * image_size == sched.protocol._published_messages[-1][1]

        sched.send_next_frame()  # Frame 1
        assert 2 == len(sched.protocol._published_messages)
        assert 'ledslie/frames/1' == sched.protocol._published_messages[-1][0]
        assert b'1' * image_size == sched.protocol._published_messages[-1][1]

        sched.send_next_frame()  # Frame 2
        assert 3 == len(sched.protocol._published_messages)
        assert 'ledslie/frames/1' == sched.protocol._published_messages[-1][0]
        assert b'2' * image_size == sched.protocol._published_messages[-1][1]
        #
        sched.send_next_frame()  # End of program!
        # assert 3 == len(sched.protocol._published_messages)
        # sched.send_next_frame()  # End of program!  # this should not happen.
        # assert 3 == len(sched.protocol._published_messages)

    def test_sequence_wrong(self, sched):
        image_size = sched.config.get('DISPLAY_SIZE')
        topic = LEDSLIE_TOPIC_SEQUENCES_UNNAMED + "/test"
        sequence = [
            ['666', {'duration': 100}],  # Wrong number of bytes in the image
        ]
        payload = json.dumps([sequence, {}]).encode()
        assert sched.catalog.is_empty()
        sched.onPublish(topic, payload, qos=0, dup=False, retain=False, msgId=0)
        assert sched.catalog.is_empty()

        sequence = [
            [SerializeFrame(b'0'*image_size), {}],  # No duration information, will default to the standard one.
        ]
        payload = json.dumps([sequence, {}]).encode()
        assert sched.catalog.is_empty()
        sched.onPublish(topic, payload, qos=0, dup=False, retain=False, msgId=0)
        assert sched.catalog.has_content()

    def test_AnimateStill(self, sched):
        seq = FrameSequence()
        img_data = bytes(bytearray(Config().get('DISPLAY_SIZE')))
        seq.add_frame(Frame(img_data, 2000))
        animated_seq = AnimateStill(seq[0])
        assert Config().get('DISPLAY_HEIGHT') == len(animated_seq)
        assert sum([frame.duration for frame in animated_seq.frames])
