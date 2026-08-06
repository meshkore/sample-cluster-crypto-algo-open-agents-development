#!/bin/sh
# Read a message aloud in Castilian Spanish.
#
# The operator asked for spoken answers. Everything written in this project
# stays English per the project rules; this is the one deliberate exception,
# because it is the operator's own ear it is addressed to.
#
# Engine order, best first, all local -- nothing here sends text anywhere:
#   1. macOS `say` with a Spanish (Spain) voice. Native, instant, no install.
#   2. espeak-ng -v es. Robotic but present on Linux and already on this Mac.
#
#   bin/speak.sh "texto"           speak it
#   echo "texto" | bin/speak.sh    speak stdin
#   VOICE=Jorge bin/speak.sh "..."  pick another es_ES voice
#   SAVE=out.aiff bin/speak.sh "..." also write the audio to a file
set -eu

TEXT=${1:-}
[ -z "$TEXT" ] && TEXT=$(cat)
[ -z "$(printf '%s' "$TEXT" | tr -d '[:space:]')" ] && { echo "speak: nothing to say" >&2; exit 2; }

VOICE=${VOICE:-Mónica}
RATE=${RATE:-180}

if command -v say >/dev/null 2>&1; then
  # Fall back to any installed es_ES voice if the requested one is absent, so a
  # fresh machine still speaks Spanish rather than silently reading it in English.
  if ! say -v '?' 2>/dev/null | grep -q "^${VOICE} "; then
    VOICE=$(say -v '?' 2>/dev/null | awk '$2=="es_ES"{print $1; exit}')
  fi
  [ -z "$VOICE" ] && VOICE="Mónica"
  if [ -n "${SAVE:-}" ]; then
    printf '%s' "$TEXT" | say -v "$VOICE" -r "$RATE" -o "$SAVE"
    echo "speak: wrote $SAVE"
  fi
  printf '%s' "$TEXT" | say -v "$VOICE" -r "$RATE"
  exit 0
fi

if command -v espeak-ng >/dev/null 2>&1; then
  printf '%s' "$TEXT" | espeak-ng -v es -s "$RATE"
  exit 0
fi

echo "speak: no local text-to-speech engine found (tried say, espeak-ng)" >&2
exit 1
