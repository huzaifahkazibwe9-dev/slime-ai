"""Strict normalization for simulated accessibility observations."""


def normalize_accessible_ids(observed):
    """Return shooter IDs from a resolver result without guessing its shape.

    None means no observed accessible shooters. Strings and mappings are
    rejected because iterating them would silently produce keys/characters.
    """
    if observed is None:
        return set()
    if isinstance(observed, (str, bytes, dict)):
        raise TypeError(
            "accessibility_resolver must return an iterable of shooter IDs, "
            "not a string or mapping"
        )
    try:
        return {str(value) for value in observed}
    except TypeError as error:
        raise TypeError(
            "accessibility_resolver must return an iterable of shooter IDs"
        ) from error
