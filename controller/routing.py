"""Pure routing policy used by the Ryu controller and unit tests."""


def offload_probability(best_private_load, threshold):
    """Return a value from 0.0 to 1.0 for gradual cloud offload."""
    if threshold <= 0:
        raise ValueError("threshold must be greater than zero")
    if best_private_load <= threshold:
        return 0.0
    return min(1.0, max(0.0, (best_private_load - threshold) / threshold))


def choose_backend(private_loads, threshold, random_value):
    """Choose the least-loaded private backend or the cloud backend."""
    if not private_loads:
        raise ValueError("at least one private backend is required")
    if not 0 <= random_value < 1:
        raise ValueError("random_value must be in the range [0, 1)")
    best_private = min(private_loads, key=private_loads.get)
    probability = offload_probability(private_loads[best_private], threshold)
    return ("h4" if probability > random_value else best_private, probability)
