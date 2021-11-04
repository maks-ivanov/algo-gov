from pyteal import Bytes, Int

CREATOR_KEY = Bytes("creator_key")
GOV_TOKEN_KEY = Bytes("gov_token_key")
PROPOSE_THRESHOLD_KEY = Bytes("propose_threshold_key")
VOTE_THRESHOLD_KEY = Bytes("vote_threshold_key")
QUORUM_THRESHOLD_KEY = Bytes("quorum_threshold_key")
STAKE_TIME_LENGTH_KEY = Bytes("stake_time_length_key")
PROPOSE_TIME_LENGTH_KEY = Bytes("propose_time_length_key")
VOTE_TIME_LENGTH_KEY = Bytes("vote_time_length_key")
EXECUTE_DELAY_KEY = Bytes("execute_delay_key")
START_TIME_KEY = Bytes("start_time_key")

NUM_REGISTERED_PROPOSALS_KEY = Bytes("num_active_proposals_key")
MAX_NUM_PROPOSALS_KEY = Bytes("max_num_proposals_key")

ADDRESS_AMOUNT_STAKED_KEY = Bytes("address_amount_staked_key")
ADDRESS_VOTING_POWER_KEY = Bytes("address_voting_power_key")
ADDRESS_PROPOSITION_POWER_KEY = Bytes("address_proposition_power_key")

GOVERNOR_ID_KEY = Bytes("governor_id_key")
TARGET_ID_KEY = Bytes("target_id_key")
REGISTRATION_ID_KEY = Bytes("registration_id_key")
FOR_VOTES_KEY = Bytes("for_votes_key")
AGAINST_VOTES_KEY = Bytes("against_votes_key")
CAN_EXECUTE_KEY = Bytes("can_execute_key")
