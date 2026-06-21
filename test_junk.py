import re
from backend.parser import _strip_junk_tags, _clean_title
text = " Suzumiya Haruhi no Yuuutsu (2009) - 01 (1920x1080 h264 BD FLAC) [367D762A]"

# 1. strip episode
text = text.replace(" - 01", "")
print("After episode:", repr(text))

text = _strip_junk_tags(text)
print("After tags:", repr(text))

text = _clean_title(text)
print("After clean:", repr(text))
