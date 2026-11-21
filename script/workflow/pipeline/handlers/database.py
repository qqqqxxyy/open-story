"""Database-level workflow results."""
def initialize(context, params): return context.repository.identity()
def info(context, params): return context.repository.info()
