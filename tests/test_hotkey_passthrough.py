import ctypes as C
from types import SimpleNamespace

import pytest

from dekstopshot.core import Hotkey
from dekstopshot.hotkeys import HotkeyManager
from dekstopshot.keyboard_hook import (
    KBDLLHOOKSTRUCT,
    WM_KEYDOWN,
    WM_KEYUP,
    WM_SYSKEYDOWN,
    PassThroughKeyboardHook,
    ShortcutMatcher,
)


def test_plain_key_is_once_per_press_and_extra_modifiers_do_not_match():
    states = {}
    matcher = ShortcutMatcher(Hotkey(), lambda vk: states.get(vk, 0))
    assert matcher.handle(WM_KEYDOWN, 0xBD)
    assert not matcher.handle(WM_KEYDOWN, 0xBD)
    assert not matcher.handle(WM_KEYUP, 0xBD)
    states[0x10] = 0x8000
    assert not matcher.handle(WM_KEYDOWN, 0xBD)
    matcher.handle(WM_KEYUP, 0xBD)
    states.clear()
    states[0x5C] = 0x8000
    assert not matcher.handle(WM_KEYDOWN, 0xBD)
    matcher.handle(WM_KEYUP, 0xBD)
    states.clear()
    assert matcher.handle(WM_KEYDOWN, 0xBD)


def test_held_modifiers_and_system_alt_match_exactly_including_injected_accessibility_input():
    states = {0x11: 0x8000}
    matcher = ShortcutMatcher(Hotkey(0x53, 3), lambda vk: states.get(vk, 0))
    # LLKHF_ALTDOWN plus generic Ctrl also covers the Windows AltGr alias.
    assert matcher.handle(WM_SYSKEYDOWN, 0x53, 0x20 | 0x10)
    matcher.handle(WM_KEYUP, 0x53)
    states[0x10] = 0x8000
    assert not matcher.handle(WM_SYSKEYDOWN, 0x53, 0x20)
    matcher.handle(WM_KEYUP, 0x53)
    states.clear()
    assert not matcher.handle(WM_KEYDOWN, 0x53)


def test_resuming_while_target_is_held_waits_until_a_fresh_press():
    matcher = ShortcutMatcher(Hotkey(0x6D), lambda vk: 0x8000 if vk == 0x6D else 0)
    assert not matcher.handle(WM_KEYDOWN, 0x6D)
    assert not matcher.handle(WM_KEYDOWN, 0xBD)  # OEM minus remains a separate key.
    matcher.handle(WM_KEYUP, 0x6D)
    assert matcher.handle(WM_KEYDOWN, 0x6D)


@pytest.mark.parametrize("fail_callback", [False, True])
def test_native_observer_always_passes_the_key_to_the_next_hook(fail_callback):
    observer = object.__new__(PassThroughKeyboardHook)
    observer._handle = 123
    observer.matcher = ShortcutMatcher(Hotkey(), lambda _vk: 0)
    chained, captures = [], []

    def on_pressed():
        captures.append(True)
        if fail_callback:
            raise RuntimeError("Qt notification failure")

    observer.on_pressed = on_pressed
    observer.user = SimpleNamespace(CallNextHookEx=lambda *args: chained.append(args) or 456)
    event = KBDLLHOOKSTRUCT(0xBD, 0, 0, 0, 0)
    address = C.addressof(event)
    assert observer._dispatch(0, WM_KEYDOWN, address) == 456
    assert observer._dispatch(0, WM_KEYDOWN, address) == 456
    assert observer._dispatch(0, WM_KEYUP, address) == 456
    assert observer._dispatch(-1, WM_KEYDOWN, 0) == 456  # Negative hook code cannot dereference lParam.
    assert captures == [True]
    assert len(chained) == 4


class FakeAPI:
    def __init__(self):
        self.bindings = {}
        self.conflict = False

    def register_hotkey(self, identifier, hotkey):
        if self.conflict:
            raise OSError("already taken")
        self.bindings[identifier] = hotkey

    def unregister_hotkey(self, identifier):
        self.bindings.pop(identifier, None)


class FakeHooks:
    def __init__(self):
        self.instances = []
        self.fail_start = False

    def __call__(self, hotkey, callback):
        owner = self

        class Observer:
            def __init__(self):
                self.hotkey, self.callback = hotkey, callback
                self.running = False
                self.fail_close = False

            def start(self):
                if owner.fail_start:
                    raise OSError("hook failed")
                self.running = True

            def close(self):
                if self.fail_close:
                    raise OSError("cannot release hook")
                self.running = False

        instance = Observer()
        self.instances.append(instance)
        return instance


def test_passthrough_uses_no_exclusive_binding_and_pause_invalidates_queued_capture(qapp):
    api, hooks = FakeAPI(), FakeHooks()
    manager = HotkeyManager(api, qapp, Hotkey(), passthrough=True, hook_factory=hooks)
    captures = []
    manager.events.capture_requested.connect(lambda: captures.append(True))
    try:
        manager.resume()
        assert manager.registered and not api.bindings
        first = hooks.instances[-1]
        first.callback()
        manager.suspend()
        qapp.processEvents()
        assert not captures and not first.running and not manager.registered
        manager.resume()
        assert hooks.instances[-1] is not first
        hooks.instances[-1].callback()
        qapp.processEvents()
        assert captures == [True]
    finally:
        manager.close()


def test_replacing_a_hook_rejects_stale_callbacks_and_preserves_old_hook_if_install_fails(qapp):
    api, hooks = FakeAPI(), FakeHooks()
    manager = HotkeyManager(api, qapp, Hotkey(), passthrough=True, hook_factory=hooks)
    captures = []
    manager.events.capture_requested.connect(lambda: captures.append(True))
    try:
        manager.resume()
        first = hooks.instances[-1]
        hooks.fail_start = True
        with pytest.raises(OSError):
            manager.replace(Hotkey(0x53, 3))
        assert manager.current == Hotkey() and first.running
        hooks.fail_start = False
        manager.replace(Hotkey(0x53, 3))
        assert not first.running and manager.current == Hotkey(0x53, 3)
        first.callback()
        hooks.instances[-1].callback()
        qapp.processEvents()
        assert captures == [True]
    finally:
        manager.close()


def test_mode_switch_conflicts_keep_working_observer_and_can_then_switch_both_ways(qapp):
    api, hooks = FakeAPI(), FakeHooks()
    manager = HotkeyManager(api, qapp, Hotkey(), passthrough=True, hook_factory=hooks)
    try:
        manager.resume()
        first = hooks.instances[-1]
        api.conflict = True
        with pytest.raises(OSError):
            manager.set_passthrough(False)
        assert manager.passthrough and manager.registered and first.running and not api.bindings
        api.conflict = False
        manager.set_passthrough(False)
        assert not first.running and not manager.passthrough and manager.registered
        assert list(api.bindings.values()) == [Hotkey()]
        hooks.fail_start = True
        with pytest.raises(OSError):
            manager.set_passthrough(True)
        assert not manager.passthrough and list(api.bindings.values()) == [Hotkey()]
        hooks.fail_start = False
        manager.set_passthrough(True)
        assert manager.passthrough and manager.registered and not api.bindings
        assert hooks.instances[-1].running
    finally:
        manager.close()


def test_failed_hook_release_rolls_back_new_exclusive_registration(qapp):
    api, hooks = FakeAPI(), FakeHooks()
    manager = HotkeyManager(api, qapp, Hotkey(), passthrough=True, hook_factory=hooks)
    try:
        manager.resume()
        observer = hooks.instances[-1]
        observer.fail_close = True
        with pytest.raises(OSError):
            manager.set_passthrough(False)
        assert observer.running and manager.passthrough and manager.registered
        assert not api.bindings
        observer.fail_close = False
    finally:
        manager.close()


def test_changing_mode_while_paused_does_not_install_an_observer(qapp):
    api, hooks = FakeAPI(), FakeHooks()
    manager = HotkeyManager(api, qapp, Hotkey(), hook_factory=hooks)
    try:
        manager.set_passthrough(True)
        assert not manager.registered and not hooks.instances and not api.bindings
        manager.resume()
        assert len(hooks.instances) == 1 and manager.registered
    finally:
        manager.close()
