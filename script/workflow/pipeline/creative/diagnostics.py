"""Bounded automatic-selection evidence; no prose, extra queries or domain decisions."""
from .projection import category


def boundary(row):
    return {'event_id': row['event']['event_id'], 'node_id': row['node_id'], 'seq': row['event']['seq']}


def selection_summary(available, candidates, chosen, strategy, *, limits=None,
                      character_counts=None, scores=None):
    result = {'strategy': strategy, 'available_count': len(available),
              'candidate_count': len(candidates), 'automatic_count': len(chosen),
              'limits': limits or {},
              'automatic_boundary': {'first': boundary(chosen[0]), 'last': boundary(chosen[-1])} if chosen else None}
    if character_counts is not None:
        result['character_counts'] = character_counts
    if scores is not None:
        selected_scores = [scores[row['event']['event_id']] for row in chosen]
        result.update(positive_match_count=sum(value > 0 for value in scores.values()),
                      zero_score_selected_count=sum(value == 0 for value in selected_scores),
                      selected_score_range=[min(selected_scores), max(selected_scores)] if selected_scores else None)
    return result


def complete_diagnostics(categories, selected_projection, pinned, **counts):
    for name, value in categories.items():
        value['explicit_count'] = sum(category(row) == name for row in pinned)
        value['selected_count'] = len(selected_projection[name])
    return {**counts, 'categories': categories}
