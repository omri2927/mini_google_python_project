from core.models import Hit

def normalize_unit_numbers(*, unit_numbers: list[int]) -> list[int]:
    return sorted(set(unit_numbers))

def merge_hits_for_same_file(*, hits: list[Hit]) -> Hit:
    if not hits:
        raise ValueError("Cannot merge an empty hits")

    total_count = sum(h.count for h in hits)

    all_units = []
    for h in hits:
        all_units.extend(h.unit_index)

    normalized_units = normalize_unit_numbers(unit_numbers=all_units)

    return Hit(
            file_id=hits[0].file_id,
            unit_index=normalized_units,
            count=total_count
        )

def normalize_postings(*, postings: list[Hit]) -> list[Hit]:
    if not postings:
        return []

    sorted_postings = sorted(postings, key=lambda h: h.file_id)

    merged_results: list[Hit] = []
    current_file_group: list[Hit] = [sorted_postings[0]]

    for next_hit in sorted_postings[1:]:
        if next_hit.file_id == current_file_group[0].file_id:
            current_file_group.append(next_hit)
        else:
            merged_results.append(merge_hits_for_same_file(hits=current_file_group))
            current_file_group = [next_hit]

    merged_results.append(merge_hits_for_same_file(hits=current_file_group))

    return sorted(merged_results, key=lambda h: (-h.count, h.file_id))

def normalize_index(*, index: dict[str, list[Hit]]) -> dict[str, list[Hit]]:
    return {
        token: normalize_postings(postings=hits)
        for token, hits in index.items()
    }