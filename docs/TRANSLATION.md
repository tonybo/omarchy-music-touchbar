# Japanese → Chinese lyrics

When timed Japanese lyrics are available, a subtle 🌐 control appears at the right
edge of the lyrics panel. Tap it to translate into Simplified Chinese: Japanese
stays on the upper line, with Chinese below it following the same timestamps,
including playback seeks. Tap again to return to the original/next-line view.
The rest of the panel still switches between lyrics and spectrum; swipes adjust
volume as before. Untimed lyrics retain the song-info view.

Translation begins only after a tap. It sends lyric text to Google Translate's
public web endpoint, with no audio or account credentials. This is a best-effort
endpoint, not the supported Google Cloud API; availability and translation quality
can vary. Results stay in a bounded memory cache until the lyrics worker exits.
Loading keeps the Japanese lyrics visible; a failed request offers tap-to-retry.

Only Japanese passages are translated. Foreign-script phrases (including English
inside a Japanese line) retain their original spelling and punctuation and are
not sent for translation. Entirely non-Japanese lines remain in the original row
without a duplicate underneath. Ambiguous lines containing only Han characters
are left untouched because their language cannot be reliably inferred from script.

