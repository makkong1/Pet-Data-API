from app.models.animal import AbandonedAnimal
from app.models.log import CollectionLog


def test_abandoned_animal_tablename():
    assert AbandonedAnimal.__tablename__ == "abandoned_animals"


def test_collection_log_tablename():
    assert CollectionLog.__tablename__ == "collection_logs"
