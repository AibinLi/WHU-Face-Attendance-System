import numpy as np
from attendance.matching import assign, cluster_faces, scores_for


def test_no_forced_match_below_threshold():
    results = assign(np.array([[0.2, 0.1], [0.1, 0.19]]))
    assert all(r['index'] is None and r['status'] == 'unknown' for r in results)


def test_collision_does_not_silently_assign_second_best():
    results = assign(np.array([[0.85, 0.4], [0.82, 0.41]]))
    accepted = [r['index'] for r in results if r['status'] == 'auto']
    assert len(accepted) == len(set(accepted)) == 1
    assert sum(r['status'] == 'review' for r in results) == 1


def test_ambiguity_is_not_accepted():
    assert assign(np.array([[0.6, 0.58]]))[0]['status'] == 'review'


def test_empty_gallery():
    assert assign(np.empty((2, 0)))[0]['status'] == 'unknown'


def test_same_photo_cannot_merge_and_chain_floor():
    faces = [dict(id='a', image_id='one', embedding=[1, 0]),
             dict(id='b', image_id='one', embedding=[1, 0]),
             dict(id='c', image_id='two', embedding=[.99, .01])]
    groups = cluster_faces(faces)
    assert len(groups) == 2
    assert not any('a' in g and 'b' in g for g in groups)


def test_multi_template_matching_and_scale_invariance():
    score = scores_for([[2, 0]], [[[1, 0], [.8, .6]], [[0, 1]]])
    assert np.allclose(score, [[.96, 0]], atol=1e-5)
