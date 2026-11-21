"""Story initialization route; logs always use the central destination."""
from script.workflow.data.story_stores import StoryStores
from ..initialization import StoryInitializer


def initialize(context, params):
    return StoryInitializer(StoryStores(context.data_root)).initialize(params)
