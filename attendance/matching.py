"""Identity matching, independent from web UI and inference runtime."""
import numpy as np
from scipy.optimize import linear_sum_assignment


def unit(x):
    x = np.asarray(x, dtype=np.float32)
    return x / np.maximum(np.linalg.norm(x, axis=-1, keepdims=True), 1e-12)


def scores_for(embeddings, templates):
    """Multi-template cosine; no online template updates from predicted identities."""
    probes = unit(embeddings)
    if not templates:
        return np.empty((len(probes), 0), dtype=np.float32)
    columns = []
    for samples in templates:
        similarities = probes @ unit(samples).T
        ordered = np.sort(similarities, axis=1)
        columns.append(ordered[:, -1] if ordered.shape[1] == 1 else
                       0.8 * ordered[:, -1] + 0.2 * ordered[:, -2])
    return np.stack(columns, axis=1)


def assign(scores, threshold=0.40, margin=0.05):
    """Hungarian assignment with individual reject columns; scores are NOT probabilities."""
    scores = np.asarray(scores, dtype=np.float32)
    n, m = scores.shape
    if not m:
        return [dict(index=None, status='unknown', score=0., margin=0., candidates=[]) for _ in range(n)]
    augmented = np.concatenate([scores, np.full((n, n), threshold - 0.001)], axis=1)
    rows, cols = linear_sum_assignment(-augmented)
    allocation = dict(zip(rows.tolist(), cols.tolist()))
    results = []
    for i, row in enumerate(scores):
        ranked = np.argsort(-row)
        first = int(ranked[0])
        gap = float(row[first] - row[ranked[1]]) if m > 1 else float(row[first])
        chosen = allocation[i]
        best = float(row[first])
        candidates = [dict(index=int(j), score=round(float(row[j]), 4)) for j in ranked[:5]]
        if best < threshold:
            status, identity, value = 'unknown', None, best
        elif chosen >= m or chosen != first:
            status, identity, value = 'review', None, best
        elif gap < margin:
            status, identity, value = 'review', None, best
        else:
            status, identity, value = 'auto', chosen, float(row[chosen])
        results.append(dict(index=identity, status=status, score=round(value, 4),
                            margin=round(gap, 4), candidates=candidates))
    return results


def cluster_faces(faces, threshold=0.43):
    """Agglomeration with same-photo cannot-link and a complete-link floor."""
    if not faces:
        return []
    emb = unit([f['embedding'] for f in faces])
    similarity = emb @ emb.T
    groups = {i: [i] for i in range(len(faces))}
    owner = list(range(len(faces)))
    edges = sorted(((float(similarity[i, j]), i, j)
                    for i in range(len(faces)) for j in range(i + 1, len(faces))
                    if similarity[i, j] >= threshold), reverse=True)
    for value, i, j in edges:
        a, b = owner[i], owner[j]
        if a == b:
            continue
        ga, gb = groups[a], groups[b]
        if {faces[k]['image_id'] for k in ga} & {faces[k]['image_id'] for k in gb}:
            continue
        cross = similarity[np.ix_(ga, gb)]
        ca, cb = unit(emb[ga].mean(0)), unit(emb[gb].mean(0))
        if float(ca @ cb) < threshold or float(cross.min()) < threshold - 0.13:
            continue
        groups[a] = ga + gb
        for k in gb:
            owner[k] = a
        del groups[b]
    return [[faces[i]['id'] for i in group] for group in groups.values()]
