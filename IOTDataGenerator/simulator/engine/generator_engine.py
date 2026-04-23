"""
Generator dispatcher — reads a single JSON field spec and returns
the correct generator instance (RandomWalk, SineWave, or StepChange).

This is the bridge between the JSON config (node_schemas.json) and
the runtime signal generators.  The NodeFactory calls build_generator()
for every field of every node type, so adding a new generator type
to the JSON requires only adding a new branch here.
"""
from generators.random_walk import RandomWalk
from generators.sine_wave import SineWave
from generators.step_change import StepChange


def build_generator(spec: dict):
    """
    Instantiate a signal generator from a JSON field-spec dict.

    Supported spec shapes
    ---------------------
    Random Walk:
        { "generator": "random_walk",
          "initial": <float>,
          "min":     <float>,
          "max":     <float>,
          "step":    <float> }

    Sine Wave:
        { "generator": "sine",
          "amplitude": <float>,
          "offset":    <float>,
          "period_s":  <float>,
          "phase_h":   <float>,   # optional, default 0
          "min":       <float>,   # optional clamp
          "max":       <float> }  # optional clamp

    Step Change:
        { "generator": "step_change",
          "states":    [<any>, ...],
          "initial":   <any>,
          "flip_prob": <float> }  # optional, default 0.02

    Returns
    -------
    RandomWalk | SineWave | StepChange instance
    """
    g = spec.get("generator")

    if g == "random_walk":
        return RandomWalk(
            initial=spec["initial"],
            lo=spec["min"],
            hi=spec["max"],
            step=spec["step"],
        )

    elif g == "sine":
        return SineWave(
            amplitude=spec["amplitude"],
            offset=spec["offset"],
            period_s=spec["period_s"],
            phase_h=spec.get("phase_h", 0.0),
            lo=spec.get("min"),
            hi=spec.get("max"),
        )

    elif g == "step_change":
        return StepChange(
            states=spec["states"],
            initial=spec["initial"],
            flip_prob=spec.get("flip_prob", 0.02),
        )

    else:
        raise ValueError(
            f"[GeneratorEngine] Unknown generator type: '{g}'. "
            f"Expected one of: random_walk, sine, step_change."
        )
