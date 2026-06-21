from backend.parser import parse_file
p = parse_file("[Doki] Suzumiya Haruhi no Yuuutsu (2009) - 01 (1920x1080 h264 BD FLAC) [367D762A].mkv")
print(p.detected_title)
