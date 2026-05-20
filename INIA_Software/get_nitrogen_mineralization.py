# mineralization.py

import unicodedata


def normalize_text(text):
    """
    Normalize text to compare safely:
    - lowercase
    - remove accents
    - remove extra spaces
    """
    text = str(text).strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = " ".join(text.split())
    return text


# ------------------------------------------------------------
# Texture groups
# ------------------------------------------------------------
TEXTURE_GROUPS = {
    "arenoso": [
        "arenoso",
        "arena franca",
        "franco arenoso",
    ],
    "franco": [
        "franco",
        "franco limoso",
        "limoso",
        "franco arcillo arenoso",
        "franco arcilloso",
    ],
    "arcilloso": [
        "franco arcillo limoso",
        "arcillo arenoso",
        "arcillo limoso",
        "arcilloso",
    ],
}


# ------------------------------------------------------------
# Mineralization table
#
# Values are in percent (%)
# ------------------------------------------------------------
MINERALIZATION_TABLE = {
    "arenoso": {
        "calido y lluvioso": 2.00,
        "calido y seco": 1.75,
        "frio y lluvioso": 1.30,
        "frio y seco": 1.45,
    },
    "franco": {
        "calido y lluvioso": 1.75,
        "calido y seco": 1.50,
        "frio y lluvioso": 1.15,
        "frio y seco": 1.30,
    },
    "arcilloso": {
        "calido y lluvioso": 1.50,
        "calido y seco": 1.25,
        "frio y lluvioso": 1.00,
        "frio y seco": 1.15,
    },
}


def get_texture_group(texture):
    """
    Convert texture name into one of:
        arenoso, franco, arcilloso
    """

    texture_norm = normalize_text(texture)

    for group, textures in TEXTURE_GROUPS.items():
        normalized_textures = [normalize_text(t) for t in textures]

        if texture_norm in normalized_textures:
            return group

    valid_textures = []
    for textures in TEXTURE_GROUPS.values():
        valid_textures.extend(textures)

    raise ValueError(
        f"Texture '{texture}' was not found.\n"
        f"Valid textures are:\n- " + "\n- ".join(valid_textures)
    )


def get_mineralization_percentage(texture, clima):
    """
    Main function.

    Parameters
    ----------
    texture : str
        Soil texture.
        Example:
            'Arenoso'
            'Arena franca'
            'Franco limoso'
            'Arcilloso'

    clima : str
        Climate.
        Example:
            'Cálido y lluvioso'
            'Cálido y seco'
            'Frío y lluvioso'
            'Frío y seco'

    Returns
    -------
    float
        Mineralization percentage.
    """

    texture_group = get_texture_group(texture)
    clima_norm = normalize_text(clima)

    if clima_norm not in MINERALIZATION_TABLE[texture_group]:
        valid_climates = list(MINERALIZATION_TABLE[texture_group].keys())

        raise ValueError(
            f"Clima '{clima}' was not found.\n"
            f"Valid climates are:\n- " + "\n- ".join(valid_climates)
        )

    return MINERALIZATION_TABLE[texture_group][clima_norm]


# ------------------------------------------------------------
# Example usage
# ------------------------------------------------------------
if __name__ == "__main__":

    texture_input = "Franco limoso"
    #texture_input = "Arenoso"
    #texture_input = "Arcilloso"
    #clima_input = "Cálido y seco"
    #clima_input = "Frio y seco"
    clima_input = "Frio y lluvioso"

    mineralization = get_mineralization_percentage(
        texture=texture_input,
        clima=clima_input,
    )

    print(f"Texture: {texture_input}")
    print(f"Clima: {clima_input}")
    print(f"Mineralization: {mineralization}%")
