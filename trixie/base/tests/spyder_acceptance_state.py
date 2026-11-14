"""Qt-independent acceptance predicate; elapsed time never grants acceptance."""


def evaluate(snapshot, expected, elapsed, timeout):
    """Return PASS, WAIT or FAIL plus a useful reason for the GUI driver."""
    reasons = []
    for key in ('ready', 'alive', 'same_console', 'pane_visible'):
        if not snapshot.get(key):
            reasons.append(key)
    kernel = snapshot.get('kernel') or {}
    for key, value in expected.items():
        if kernel.get(key) != value:
            reasons.append('kernel.' + key)
    for key in ('array_test', 'polygon_area'):
        if key not in snapshot.get('source', {}):
            reasons.append('source.' + key)
        if key not in snapshot.get('rows', []):
            reasons.append('visible.' + key)
    # Once expired, even late data cannot turn this attempt into a success.
    if elapsed >= timeout:
        return 'FAIL', 'deadline: ' + ', '.join(reasons or ['late result'])
    return ('WAIT', ', '.join(reasons)) if reasons else ('PASS', 'kernel and GUI')
