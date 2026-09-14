import re

# Pagination and query helpers shared by list pages on user and admin sides.
MAX_SEARCH_LENGTH = 80


def clean_search(value, max_length=MAX_SEARCH_LENGTH):
    value = str(value or "").strip()
    return value[:max_length]


def contains_regex(value, max_length=MAX_SEARCH_LENGTH):
    cleaned = clean_search(value, max_length=max_length)
    return {"$regex": re.escape(cleaned), "$options": "i"}


def exact_regex(value, max_length=40):
    cleaned = clean_search(value, max_length=max_length)
    return {"$regex": f"^{re.escape(cleaned)}$", "$options": "i"}


def _clamp_int(value, default, min_value=1, max_value=10_000):
    try:
        n = int(value)
    except Exception:
        return default
    return max(min_value, min(max_value, n))


def get_pagination_args(request, default_per_page=20, max_per_page=50):
    page = _clamp_int(request.args.get("page", 1), 1, 1, 1_000_000)
    per_page = _clamp_int(request.args.get("per_page", default_per_page), default_per_page, 1, max_per_page)
    skip = (page - 1) * per_page
    return page, per_page, skip


def page_meta(total_count, page, per_page):
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    return {
        "page": page,
        "per_page": per_page,
        "total": total_count,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_page": page - 1,
        "next_page": page + 1,
    }
