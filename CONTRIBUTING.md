# Contributing

Bug reports, hardware validation, and pull requests are welcome.

For a hardware report, include the Mac model, Touch Bar DRM mode, tiny-dfr version, Omarchy version, and whether the issue concerns display updates, taps, swipes, or suspend. Do not include authentication tokens or your full home configuration. Relevant service logs are usually enough.

Run the tests before submitting a change:

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q src tools
```

The most valuable checks are:

- Tap versus horizontal swipe, including reversing direction and returning to the start.
- Contacts with no changed Y coordinate and repeated contacts in the same slot.
- No action for an unrelated button or multi-finger gesture.
- Volume clamping, coalescing, and live feedback before finger-up.
- Long Unicode titles, XML escaping, invalid/oversized metadata, and expired feedback.
- Device disconnect/reconnect, Fn-layer switching, and suspend/resume.
- Installation and removal on a clean machine, preserving existing user configuration.

Keep raw input access narrow, never execute stream metadata, and do not make system configuration user-writable to simplify rendering. Rendering changes should preserve the protected service boundary.

Useful future directions include a native tiny-dfr image-refresh interface, broader hardware detection, MPRIS media sources, configurable gestures, and a graphical preferences page.
