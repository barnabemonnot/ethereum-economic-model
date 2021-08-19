"""Experiment template example
An example of overriding and customizing the default experiment to create a new template.
"""

import copy
from collections import defaultdict

from experiments.default_experiment import experiment
from experiments.utils import rng_generator

import model.constants as constants
import model.state_variables as state_variables

rng_generator(123)
SYNC_COMMITTEE_SIZE = 512
EPOCHS_PER_SYNC_COMMITTEE_PERIOD = 256

# Make a copy of the default experiment to avoid mutation
experiment = copy.deepcopy(experiment)

parameter_overrides = {
    "dt": [1],
    "validator_process": [lambda _run, _timestep: 0],
    "eip1559_tip_process": [lambda _run, _timestep: 2], # Gwei per gas unit
    "mev_process": [lambda _run, _timestep: rng_generator().exponential(0.05)], # ETH per block
    "validator_uptime_process": [lambda _run, _timestep: 1.0],
}
assert all([EPOCHS_PER_SYNC_COMMITTEE_PERIOD % dt == 0 for dt in parameter_overrides["dt"]]), "Step duration must divide sync committee period"

n_validators = 100000

state_variable_overrides = {
    "eth_price": 1000,
    "individual_validator_rewards": [0] * n_validators,
    "sync_committee": [],
    "number_of_validators": n_validators,
}

def update_sync_committee(params, substep, state_history, previous_state, policy_input):
    rng = rng_generator()
    
    dt = params["dt"]
    
    current_epoch = previous_state["timestep"] * dt
    number_of_validators = previous_state["number_of_validators"]
    sync_committee = previous_state["sync_committee"]
    
    if ((current_epoch-1) % EPOCHS_PER_SYNC_COMMITTEE_PERIOD == 0):
        sync_committee = rng.choice(number_of_validators, size=SYNC_COMMITTEE_SIZE)

    return "sync_committee", sync_committee

def reward_validators(params, substep, state_history, previous_state, policy_input):
    rng = rng_generator()
    
    dt = params["dt"]
    gas_target_process = params["gas_target_process"]
    eip1559_tip_process = params["eip1559_tip_process"]
    mev_process = params["mev_process"]
    
    run = previous_state["run"]
    timestep = previous_state["timestep"]
    number_of_validators = previous_state["number_of_validators"]
    individual_validator_rewards = previous_state["individual_validator_rewards"]
    sync_committee = previous_state["sync_committee"]
    source_reward = previous_state["source_reward"]
    target_reward = previous_state["target_reward"]
    head_reward = previous_state["head_reward"]
    sync_reward = previous_state["sync_reward"]
    block_proposer_reward = previous_state["block_proposer_reward"]
    
    ### SYNC
    sync_reward_per_validator = sync_reward / SYNC_COMMITTEE_SIZE
    
    for vi in sync_committee:
        individual_validator_rewards[vi] += sync_reward_per_validator
    
    ### ATTESTATIONS
    attestation_rewards = source_reward + target_reward + head_reward
    attestation_rewards_per_validator = attestation_rewards / number_of_validators
    
    for vi in range(number_of_validators):
        individual_validator_rewards[vi] += attestation_rewards_per_validator
        
    ### PROPOSALS
    proposers_per_timestep = constants.slots_per_epoch * dt
    proposers = rng.choice(number_of_validators, size=proposers_per_timestep)
    
    reward_per_proposer = block_proposer_reward / proposers_per_timestep
    reward_per_proposer += eip1559_tip_process(run, timestep * dt) * gas_target_process(run, timestep * dt)
    reward_per_proposer += mev_process(run, timestep * dt)
    
    for vi in proposers:
        individual_validator_rewards[vi] += reward_per_proposer
            
    return "individual_validator_rewards", individual_validator_rewards

extra_psubs = [
    {
        "policies": {
            
        },
        "variables": {
            "sync_committee": update_sync_committee
        }
    },
    {
        "policies": {
            
        },
        "variables": {
            "individual_validator_rewards": reward_validators
        }
    }
]

n_years = 1

# Override default experiment System Parameters
experiment.simulations[0].model.params.update(parameter_overrides)
# Override default experiment Initial State
experiment.simulations[0].model.initial_state.update(state_variable_overrides)
# Override default experiment state update blocks
experiment.simulations[0].model.state_update_blocks += extra_psubs
# Run n_years years, 1 timestep per epoch
experiment.simulations[0].timesteps = n_years * constants.epochs_per_year
