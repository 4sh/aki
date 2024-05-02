import uuid


def format_aki_container_name(fragment_name: str):
    return f'aki_{fragment_name}_{uuid.uuid4().hex}'
