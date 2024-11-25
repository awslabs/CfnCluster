#!/bin/bash

DISALLOWED_PATTERNS=(
  "amazonaws\.com"
  "amazonaws\.com\.cn"
  "c2s\.ic\.gov"
  "sc2s\.sgov\.gov"
)

FILE_TYPES="*.py *.sh"

EXIT_STATUS=0

echo "Scanning for disallowed URL suffixes..."

for FILE_TYPE in $FILE_TYPES; do
  FILES=$(git ls-files -- $FILE_TYPE)

  for FILE in $FILES; do
    for PATTERN in "${DISALLOWED_PATTERNS[@]}"; do
      if grep -E -q "$PATTERN" "$FILE"; then
        echo "Disallowed pattern '$PATTERN' found in file: $FILE"
        EXIT_STATUS=1
      fi
    done
  done
done

if [ $EXIT_STATUS -eq 0 ]; then
  echo "No disallowed URL suffixes found."
else
  echo "Disallowed URL suffixes detected!"
  exit $EXIT_STATUS
fi
