from telethon.tl import types

from .log_utils import log


def wrap(text, marker, end=None) -> str:
    # WhatsApp ignores markers next to whitespace, so keep it outside them.
    stripped = text.strip()
    if not stripped:
        return text
    start = text[: len(text) - len(text.lstrip())]
    tail = text[len(text.rstrip()) :]
    return f"{start}{marker}{stripped}{end or marker}{tail}"


def rich_text_to_whatsapp(obj) -> str:
    if obj is None or isinstance(obj, types.TextEmpty):
        return ""

    # Some fields (PageRelatedArticle.title, TextWithEntities.text) are plain str.
    if isinstance(obj, str):
        return obj

    if isinstance(obj, types.TextPlain):
        return obj.text

    if isinstance(obj, types.TextConcat):
        return "".join(rich_text_to_whatsapp(part) for part in obj.texts)

    if isinstance(obj, types.TextBold):
        return wrap(rich_text_to_whatsapp(obj.text), "*")

    if isinstance(obj, (types.TextItalic, types.TextUnderline)):
        return wrap(rich_text_to_whatsapp(obj.text), "_")

    if isinstance(obj, types.TextStrike):
        return wrap(rich_text_to_whatsapp(obj.text), "~")

    if isinstance(obj, types.TextFixed):
        return wrap(rich_text_to_whatsapp(obj.text), "`")

    if isinstance(obj, types.TextSpoiler):
        return rich_text_to_whatsapp(obj.text)

    if isinstance(obj, types.TextCustomEmoji):
        return obj.alt

    if isinstance(obj, types.TextImage):
        return ""

    if isinstance(obj, types.TextMath):
        return obj.source

    if isinstance(obj, types.TextDiff):
        return rich_text_to_whatsapp(obj.text)

    # Links and other wrappers.
    if hasattr(obj, "text"):
        return rich_text_to_whatsapp(obj.text)

    return ""


def caption_to_whatsapp(caption) -> str:
    if caption is None:
        return ""

    # PageBlockBlockquoteBlocks uses a plain RichText caption.
    if not isinstance(caption, types.PageCaption):
        return rich_text_to_whatsapp(caption)

    parts = [
        rich_text_to_whatsapp(caption.text),
        rich_text_to_whatsapp(caption.credit),
    ]

    return "\n".join(part for part in parts if part)


def list_item_prefix(item) -> str:
    if getattr(item, "checkbox", None):
        return "[x] " if item.checked else "[ ] "
    if isinstance(
        item, (types.PageListOrderedItemText, types.PageListOrderedItemBlocks)
    ):
        return f"{item.num}. " if item.num else "- "
    return "- "


def list_item_to_whatsapp(item) -> str:
    if isinstance(item, (types.PageListItemText, types.PageListOrderedItemText)):
        return list_item_prefix(item) + rich_text_to_whatsapp(item.text)

    if isinstance(item, (types.PageListItemBlocks, types.PageListOrderedItemBlocks)):
        content = "\n".join(
            text
            for text in (page_block_to_whatsapp(block) for block in item.blocks)
            if text
        )
        return list_item_prefix(item) + content if content else ""

    return ""


def page_block_to_whatsapp(block) -> str:
    # Headings become bold.
    if isinstance(
        block,
        (
            types.PageBlockTitle,
            types.PageBlockHeading1,
            types.PageBlockHeading2,
            types.PageBlockHeading3,
            types.PageBlockHeading4,
            types.PageBlockHeading5,
            types.PageBlockHeading6,
        ),
    ):
        text = rich_text_to_whatsapp(block.text)
        return f"*{text}*" if text else ""

    # Ordinary text blocks.
    if isinstance(
        block,
        (
            types.PageBlockParagraph,
            types.PageBlockSubtitle,
            types.PageBlockHeader,
            types.PageBlockSubheader,
            types.PageBlockKicker,
            types.PageBlockFooter,
            types.PageBlockThinking,
        ),
    ):
        return rich_text_to_whatsapp(block.text)

    if isinstance(block, types.PageBlockPreformatted):
        text = rich_text_to_whatsapp(block.text)
        return f"```{text}```" if text else ""

    # Quotes.
    if isinstance(
        block,
        (
            types.PageBlockBlockquote,
            types.PageBlockPullquote,
        ),
    ):
        text = rich_text_to_whatsapp(block.text)
        return "\n".join(f"> {line}" for line in text.splitlines())

    # Lists.
    if isinstance(
        block,
        (
            types.PageBlockList,
            types.PageBlockOrderedList,
        ),
    ):
        return "\n".join(
            text
            for text in (list_item_to_whatsapp(item) for item in block.items)
            if text
        )

    # Nested blocks.
    if isinstance(
        block,
        (
            types.PageBlockBlockquoteBlocks,
            types.PageBlockCollage,
            types.PageBlockCover,
            types.PageBlockDetails,
            types.PageBlockEmbedPost,
            types.PageBlockSlideshow,
        ),
    ):
        parts = []

        # Details: the summary goes above the hidden body.
        title = getattr(block, "title", None)
        if title is not None:
            text = rich_text_to_whatsapp(title)
            if text:
                parts.append(f"*{text}*")

        cover = getattr(block, "cover", None)
        if cover is not None:
            parts.append(page_block_to_whatsapp(cover))

        for field in ("blocks", "items"):
            for child in getattr(block, field, None) or []:
                parts.append(
                    page_block_to_whatsapp(child)
                    if isinstance(child, types.TypePageBlock)
                    else list_item_to_whatsapp(child)
                )

        caption = getattr(block, "caption", None)
        if caption is not None:
            text = caption_to_whatsapp(caption)
            if text:
                parts.append(text)

        return "\n".join(part for part in parts if part)

    # Tables.
    if isinstance(block, types.PageBlockTable):
        parts = []

        title = rich_text_to_whatsapp(block.title)
        if title:
            parts.append(f"*{title}*")

        for row in block.rows:
            cells = [rich_text_to_whatsapp(cell.text) for cell in row.cells]
            parts.append(" | ".join(cells))

        return "\n".join(parts)

    # Math.
    if isinstance(block, types.PageBlockMath):
        return block.source

    # Media captions.
    if isinstance(
        block,
        (
            types.PageBlockAudio,
            types.PageBlockDocument,
            types.PageBlockMap,
            types.PageBlockPhoto,
            types.PageBlockVideo,
            types.PageBlockEmbed,
        ),
    ):
        return caption_to_whatsapp(block.caption)

    if isinstance(block, types.PageBlockRelatedArticles):
        parts = []

        title = rich_text_to_whatsapp(block.title)
        if title:
            parts.append(f"*{title}*")

        for article in block.articles:
            title = rich_text_to_whatsapp(getattr(article, "title", None))
            if title:
                parts.append(f"- {title}")

        return "\n".join(parts)

    if isinstance(block, types.PageBlockAuthorDate):
        return rich_text_to_whatsapp(block.author)

    # These blocks have no useful plain-text representation.
    if isinstance(
        block,
        (
            types.PageBlockAnchor,
            types.PageBlockButtonRow,
            types.PageBlockChannel,
            types.PageBlockDivider,
            types.PageBlockUnsupported,
        ),
    ):
        return ""

    log(e=f"Unhandled PageBlock: {type(block).__name__}", warning=True)
    text = getattr(block, "text", None)
    return rich_text_to_whatsapp(text) if text is not None else ""


def rich_message_to_whatsapp(message) -> str:
    return "\n\n".join(
        text
        for text in (page_block_to_whatsapp(block) for block in message.blocks)
        if text
    )
