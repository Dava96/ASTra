"""JavaScript helpers for browser interactions."""

DOM_EXTRACTION_SCRIPT = """
(maxDepth) => {
    function extractElement(el, depth) {
        if (depth > maxDepth) return null;
        const tag = el.tagName.toLowerCase();
        if (['script', 'style', 'noscript', 'svg'].includes(tag)) return null;

        const result = {
            tag: tag,
            id: el.id || null,
            classes: Array.from(el.classList),
            role: el.getAttribute('role'),
            attributes: {}
        };

        ['href', 'src', 'alt', 'type', 'name', 'aria-label'].forEach(attr => {
            if (el.hasAttribute(attr)) result.attributes[attr] = el.getAttribute(attr);
        });

        const directText = Array.from(el.childNodes)
            .filter(n => n.nodeType === Node.TEXT_NODE)
            .map(n => n.textContent.trim())
            .join(' ').slice(0, 100);
        if (directText) result.text = directText;

        result.children = Array.from(el.children)
            .map(child => extractElement(child, depth + 1))
            .filter(c => c !== null);
        return result;
    }
    return extractElement(document.body, 0);
}
"""
