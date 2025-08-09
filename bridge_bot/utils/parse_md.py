from telethon.extensions import markdown  # Telethon’s own parse
from telethon.types import MessageEntityBlockquote


def parse(raw: str):
    # 1) Break raw into lines, build quote_map & stripped_lines
    raw_lines = raw.splitlines(keepends=True)
    quote_map = []
    stripped_lines = []
    for line in raw_lines:
        if line.startswith("> "):
            quote_map.append(True)
            stripped_lines.append(line[2:])
        elif line.startswith(">"):
            quote_map.append(True)
            stripped_lines.append(line[1:])
        else:
            quote_map.append(False)
            stripped_lines.append(line)

    # 2) Rejoin and run Telethon's parser
    stripped = "".join(stripped_lines)
    cleaned, md_entities = markdown.parse(stripped)

    # 3) Split cleaned into lines (keepends so offsets align)
    cleaned_lines = cleaned.splitlines(keepends=True)

    # 4) Build blockquote entities by merging contiguous quote_map
    quote_ents = []
    offset = 0
    current_start = None

    for is_quote, line in zip(quote_map, cleaned_lines):
        length = len(line)
        if is_quote:
            if current_start is None:
                current_start = offset
            # continue block until a non-quote
        else:
            if current_start is not None:
                quote_ents.append(
                    MessageEntityBlockquote(current_start, offset + 0 - current_start)
                )
                current_start = None
        offset += length

    # finalize last block
    if current_start is not None:
        quote_ents.append(
            MessageEntityBlockquote(current_start, offset - current_start)
        )

    # 5) Return cleaned text plus combined entities
    return cleaned, quote_ents + md_entities
