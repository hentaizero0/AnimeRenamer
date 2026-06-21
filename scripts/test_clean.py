import re
text = "Title (2009)"
text = re.sub(r"\s*[\])}]+\s*$", "", text)
print(repr(text))
