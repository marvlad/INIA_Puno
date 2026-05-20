# nutrient_efficiency.py

import unicodedata


NUTRIENTS = ["N", "P", "K", "Ca", "Mg", "S"]


def normalize_text(text):
    """
    Normalize text to compare texture names safely.
    Example:
        'Franco arcillo arenoso' -> 'franco arcillo arenoso'
        'Arcilloso' -> 'arcilloso'
    """
    text = str(text).strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
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
# Efficiency table
#
# Each pH interval has:
#   (ph_min, ph_max, efficiencies)
#
# efficiencies are written as:
#   nutrient: (minimum_efficiency, maximum_efficiency)
#
# For pH < 5.0, I use 0.0 to 5.0
# For pH > 8.5, I use 8.5 to 14.0
# ------------------------------------------------------------
EFFICIENCY_TABLE = {
    "arenoso": [
        (0.0, 5.0, {
            "N": (15, 25),
            "P": (5, 15),
            "K": (30, 40),
            "Ca": (30, 40),
            "Mg": (30, 40),
            "S": (20, 30),
        }),
        (5.1, 6.5, {
            "N": (20, 40),
            "P": (10, 20),
            "K": (40, 50),
            "Ca": (35, 50),
            "Mg": (35, 50),
            "S": (25, 40),
        }),
        (6.6, 7.3, {
            "N": (30, 50),
            "P": (20, 30),
            "K": (50, 60),
            "Ca": (45, 60),
            "Mg": (45, 60),
            "S": (30, 50),
        }),
        (7.4, 8.5, {
            "N": (20, 35),
            "P": (15, 25),
            "K": (40, 55),
            "Ca": (40, 55),
            "Mg": (40, 55),
            "S": (25, 45),
        }),
        (8.5, 14.0, {
            "N": (15, 30),
            "P": (5, 20),
            "K": (30, 50),
            "Ca": (30, 50),
            "Mg": (30, 50),
            "S": (20, 40),
        }),
    ],

    "franco": [
        (0.0, 5.0, {
            "N": (20, 30),
            "P": (10, 15),
            "K": (35, 45),
            "Ca": (35, 45),
            "Mg": (35, 45),
            "S": (25, 35),
        }),
        (5.1, 6.5, {
            "N": (25, 45),
            "P": (15, 25),
            "K": (45, 55),
            "Ca": (40, 55),
            "Mg": (40, 55),
            "S": (30, 45),
        }),
        (6.6, 7.3, {
            "N": (35, 50),
            "P": (25, 30),
            "K": (55, 60),
            "Ca": (50, 60),
            "Mg": (50, 60),
            "S": (35, 50),
        }),
        (7.4, 8.5, {
            "N": (25, 40),
            "P": (20, 30),
            "K": (45, 60),
            "Ca": (45, 60),
            "Mg": (45, 60),
            "S": (30, 50),
        }),
        (8.5, 14.0, {
            "N": (20, 35),
            "P": (10, 25),
            "K": (35, 55),
            "Ca": (35, 55),
            "Mg": (35, 55),
            "S": (25, 45),
        }),
    ],

    "arcilloso": [
        (0.0, 5.0, {
            "N": (25, 35),
            "P": (15, 20),
            "K": (40, 50),
            "Ca": (40, 50),
            "Mg": (40, 50),
            "S": (30, 40),
        }),
        (5.1, 6.5, {
            "N": (30, 50),
            "P": (20, 30),
            "K": (50, 60),
            "Ca": (45, 60),
            "Mg": (45, 60),
            "S": (35, 50),
        }),
        (6.6, 7.3, {
            "N": (40, 50),
            "P": (25, 30),
            "K": (55, 60),
            "Ca": (50, 60),
            "Mg": (50, 60),
            "S": (40, 50),
        }),
        (7.4, 8.5, {
            "N": (30, 45),
            "P": (20, 30),
            "K": (50, 60),
            "Ca": (45, 60),
            "Mg": (45, 60),
            "S": (35, 50),
        }),
        (8.5, 14.0, {
            "N": (25, 40),
            "P": (15, 25),
            "K": (40, 55),
            "Ca": (40, 55),
            "Mg": (40, 55),
            "S": (30, 45),
        }),
    ],
}


def get_texture_group(texture):
    """
    Convert a texture name into one of:
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


def interpolate_value(ph, ph_min, ph_max, value_min, value_max):
    """
    Linear interpolation.

    Example:
        pH interval: 0.0 to 5.0
        efficiency range: 15 to 25

        pH = 0.0 gives 15
        pH = 5.0 gives 25
        pH = 2.5 gives 20
    """

    if ph <= ph_min:
        return value_min

    if ph >= ph_max:
        return value_max

    fraction = (ph - ph_min) / (ph_max - ph_min)

    return value_min + fraction * (value_max - value_min)


def get_ph_interval(ph, texture_group):
    """
    Select the correct pH interval from the table.
    """

    intervals = EFFICIENCY_TABLE[texture_group]

    for ph_min, ph_max, values in intervals:
        if ph_min <= ph <= ph_max:
            return ph_min, ph_max, values

    # Handle small gaps in the table, for example 5.0 to 5.1
    if 5.0 < ph < 5.1:
        return intervals[1]

    if 6.5 < ph < 6.6:
        return intervals[2]

    if 7.3 < ph < 7.4:
        return intervals[3]

    raise ValueError("pH is outside the valid range. Use a pH between 0 and 14.")


def get_efficiencies(ph, texture, decimals=2):
    """
    Main function.

    Parameters
    ----------
    ph : float
        Soil pH.

    texture : str
        Soil texture, for example:
        'Arenoso', 'Franco limoso', 'Arcilloso', etc.

    decimals : int
        Number of decimals in the output.

    Returns
    -------
    dict
        Efficiencies for N, P, K, Ca, Mg, and S.
    """

    ph = float(ph)

    if ph < 0 or ph > 14:
        raise ValueError("pH must be between 0 and 14.")

    texture_group = get_texture_group(texture)

    ph_min, ph_max, values = get_ph_interval(ph, texture_group)

    results = {}

    for nutrient in NUTRIENTS:
        value_min, value_max = values[nutrient]

        interpolated = interpolate_value(
            ph=ph,
            ph_min=ph_min,
            ph_max=ph_max,
            value_min=value_min,
            value_max=value_max,
        )

        results[nutrient] = round(interpolated, decimals)

    return results


# ------------------------------------------------------------
# Example usage
# ------------------------------------------------------------
if __name__ == "__main__":

    ph_input = 6.7
    texture_input = "Franco"

    efficiencies = get_efficiencies(
        ph=ph_input,
        texture=texture_input,
        decimals=0,
    )

    print(f"pH: {ph_input}")
    print(f"Texture: {texture_input}")
    print("Efficiencies (%):")

    for nutrient, value in efficiencies.items():
        print(f"  {nutrient}: {value}")
