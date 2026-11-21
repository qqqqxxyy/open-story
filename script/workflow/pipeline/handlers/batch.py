"""Same-database batch with explicit final transaction outcome logs."""
def execute(context, params):
    trace = getattr(context, 'trace', None)
    if trace: trace('transaction.started', function=__name__ + ':execute')
    try:
        with context.repository.transaction():
            results = [context.execute(command) for command in params['commands']]
    except Exception:
        if trace: trace('transaction.rolled_back', function=__name__ + ':execute')
        raise
    if trace: trace('transaction.committed', function=__name__ + ':execute')
    return results
