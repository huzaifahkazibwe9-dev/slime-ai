# Source-image verification test matrix

The labelled-colour evaluator's `--source-image` check verifies the source
screenshot from one byte snapshot.

| Case | Expected result |
| --- | --- |
| Correct image bytes and matching dimensions | Accept; record both checks |
| Different image bytes | Reject SHA-256 mismatch |
| Correct bytes but template dimensions reversed or otherwise wrong | Reject dimension mismatch |
| Matching digest for unreadable image bytes | Reject unreadable image |
| No recorded source hash | Reject source-image verification |
| No image dimensions in an older hand-authored dataset | Verify digest only; report dimensions unchecked |

These checks establish that the supplied source file matches the template's
recorded file identity and dimensions. They do not independently validate the
sample RGB values, board-cell coordinates, human-assigned labels, or gameplay
colour mapping.

Live gameplay actions and purchases remain disabled.
