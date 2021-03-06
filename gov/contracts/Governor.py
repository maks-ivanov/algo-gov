from gov.contracts.helpers import *
from gov.contracts.config import *

algo_holding = AssetHolding.balance(Global.current_application_address(), Int(0))

start_time_exists = App.globalGetEx(Global.current_application_id(), START_TIME_KEY)

stake_time_start = App.globalGet(START_TIME_KEY)
stake_time_end = stake_time_start + App.globalGet(STAKE_PERIOD_DURATION_KEY)

propose_time_start = stake_time_end
propose_time_end = propose_time_start + App.globalGet(PROPOSE_PERIOD_DURATION_KEY)

vote_time_start = propose_time_end
vote_time_end = vote_time_start + App.globalGet(VOTE_PERIOD_DURATION_KEY)

execute_delay_time_start = vote_time_end
execute_delay_time_end = execute_delay_time_start + App.globalGet(
    EXECUTE_DELAY_DURATION_KEY
)

claim_time_start = execute_delay_time_end
claim_time_end = claim_time_start + App.globalGet(CLAIM_PERIOD_DURATION_KEY)


def stake_program():
    gov_token_txn_index = Txn.group_index() - Int(1)

    address_amount_staked = App.localGetEx(
        Txn.sender(), Global.current_application_id(), ADDRESS_AMOUNT_STAKED_KEY
    )

    on_stake = Seq(
        address_amount_staked,
        Assert(validateTokenReceived(gov_token_txn_index, GOV_TOKEN_KEY)),
        Assert(validateInTimePeriod(stake_time_start, stake_time_end)),
        If(Not(address_amount_staked.hasValue())).Then(
            Seq(
                App.localPut(
                    Txn.sender(),
                    ADDRESS_AMOUNT_STAKED_KEY,
                    Gtxn[gov_token_txn_index].asset_amount(),
                ),
                App.localPut(
                    Txn.sender(),
                    ADDRESS_VOTING_POWER_KEY,
                    Gtxn[gov_token_txn_index].asset_amount(),
                ),
                App.localPut(
                    Txn.sender(),
                    ADDRESS_PROPOSITION_POWER_KEY,
                    Gtxn[gov_token_txn_index].asset_amount(),
                ),
                App.localPut(
                    Txn.sender(), GOV_CYCLE_ID_KEY, App.globalGet(GOV_CYCLE_ID_KEY)
                ),
                Approve(),
            )
        ),
        # right now can only stake once but that may change
        Reject(),
    )

    return on_stake


def rollover():
    """
    Update user governance powers if the user has staked in the previous cycle and
    has not claimed during previous claim period
    """
    i = ScratchVar(TealType.uint64)
    return Seq(
        If(
            App.localGet(Txn.sender(), GOV_CYCLE_ID_KEY)
            != App.globalGet(GOV_CYCLE_ID_KEY)
        ).Then(
            Seq(
                # undo all delegation
                App.localPut(
                    Txn.sender(),
                    ADDRESS_VOTING_POWER_KEY,
                    App.localGet(Txn.sender(), ADDRESS_AMOUNT_STAKED_KEY),
                ),
                App.localPut(
                    Txn.sender(),
                    ADDRESS_PROPOSITION_POWER_KEY,
                    App.localGet(Txn.sender(), ADDRESS_AMOUNT_STAKED_KEY),
                ),
                # remove has_voted flags for each proposal
                For(
                    i.store(Int(0)),
                    i.load() < App.globalGet(MAX_NUM_PROPOSALS_KEY),
                    i.store(i.load() + Int(1)),
                ).Do(App.localDel(Txn.sender(), Itob(i.load()))),
                # update user's cycle
                App.localPut(
                    Txn.sender(), GOV_CYCLE_ID_KEY, App.globalGet(GOV_CYCLE_ID_KEY)
                ),
            )
        )
    )


@Subroutine(TealType.uint64)
def try_delegate_by_type(power_type_key: TealType.bytes):
    address_voting_power = App.localGetEx(
        Txn.sender(), Global.current_application_id(), power_type_key
    )

    delegate_address_id = Int(1)
    delegate_address_power = App.localGetEx(
        delegate_address_id, Global.current_application_id(), power_type_key
    )

    on_delegate = Seq(
        rollover(),
        address_voting_power,
        delegate_address_power,
        If(
            And(
                validateInTimePeriod(stake_time_start, stake_time_end),
                address_voting_power.hasValue(),
                address_voting_power.value() > Int(0),  # redundant
                # can only delegate to an address that hasn't delegated their votes out
                delegate_address_power.hasValue(),
                delegate_address_power.value() > Int(0),
            )
        ).Then(
            Seq(
                App.localPut(
                    delegate_address_id,
                    power_type_key,
                    delegate_address_power.value() + address_voting_power.value(),
                ),
                App.localPut(Txn.sender(), power_type_key, Int(0)),
                Return(Int(1)),
            )
        ),
        Return(Int(0)),
    )

    return on_delegate


def register_proposal_program():
    proposal_app_id = Int(1)
    address_proposition_power = App.localGetEx(
        Txn.sender(), Global.current_application_id(), ADDRESS_PROPOSITION_POWER_KEY
    )
    proposal_governor_id = App.globalGetEx(proposal_app_id, GOVERNOR_ID_KEY)

    num_registered_proposals = App.globalGet(NUM_REGISTERED_PROPOSALS_KEY)

    on_register_proposal = Seq(
        rollover(),
        address_proposition_power,
        proposal_governor_id,
        # check that it is proposition time
        Assert(validateInTimePeriod(propose_time_start, propose_time_end)),
        # check that address has enough power to propose
        Assert(address_proposition_power.hasValue()),
        Assert(
            address_proposition_power.value() >= App.globalGet(PROPOSE_THRESHOLD_KEY)
        ),
        Assert(proposal_governor_id.hasValue()),
        Assert(proposal_governor_id.value() == Global.current_application_id()),
        Assert(num_registered_proposals < App.globalGet(MAX_NUM_PROPOSALS_KEY)),
        register_proposal(num_registered_proposals),
        App.globalPut(NUM_REGISTERED_PROPOSALS_KEY, num_registered_proposals + Int(1)),
        # consume proposition power
        App.localPut(
            Txn.sender(),
            ADDRESS_PROPOSITION_POWER_KEY,
            address_proposition_power.value() - App.globalGet(PROPOSE_THRESHOLD_KEY),
        ),
        Approve(),
    )

    return on_register_proposal


def begin_new_governance_cycle_program():
    """
    Reset after the previous governance cycle has completed
    """
    i = ScratchVar(TealType.uint64)
    return Seq(
        start_time_exists,
        If(
            And(
                start_time_exists.hasValue(),
                Global.latest_timestamp() > claim_time_end,
            )
        ).Then(
            Seq(
                App.globalPut(
                    GOV_CYCLE_ID_KEY, App.globalGet(GOV_CYCLE_ID_KEY) + Int(1)
                ),
                For(
                    i.store(Int(0)),
                    i.load() < App.globalGet(NUM_REGISTERED_PROPOSALS_KEY),
                    i.store(i.load() + Int(1)),
                ).Do(unregister_proposal(i.load())),
                App.globalPut(NUM_REGISTERED_PROPOSALS_KEY, Int(0)),
                App.globalPut(START_TIME_KEY, Global.latest_timestamp()),
                Approve(),
            )
        ),
        Reject(),
    )


def vote_program():
    proposal_app_id = Txn.applications[1]
    proposal_registration_key = App.globalGetEx(Int(1), REGISTRATION_ID_KEY)

    registered_proposal_app_id = App.globalGetEx(
        Global.current_application_id(), proposal_registration_key.value()
    )

    has_voted = App.localGetEx(
        Txn.sender(), Global.current_application_id(), proposal_registration_key.value()
    )

    address_voting_power = App.localGetEx(
        Txn.sender(), Int(0), ADDRESS_VOTING_POWER_KEY
    )

    vote_value = Btoi(Txn.application_args[1])

    proposal_for_votes_key = Concat(
        proposal_registration_key.value(),
        Bytes("_"),
        FOR_VOTES_KEY,
    )

    proposal_against_votes_key = Concat(
        proposal_registration_key.value(),
        Bytes("_"),
        AGAINST_VOTES_KEY,
    )

    return Seq(
        rollover(),
        proposal_registration_key,
        registered_proposal_app_id,
        has_voted,
        address_voting_power,
        If(
            And(
                # proposal is registered
                registered_proposal_app_id.value() == proposal_app_id,
                # user has not voted yet
                Not(has_voted.hasValue()),
                # enough voting power to participate
                address_voting_power.value() >= App.globalGet(VOTE_THRESHOLD_KEY),
                # in voting period
                validateInTimePeriod(vote_time_start, vote_time_end),
            )
        ).Then(
            Seq(
                If(vote_value > Int(0))
                .Then(
                    App.globalPut(
                        proposal_for_votes_key,
                        App.globalGet(proposal_against_votes_key)
                        + address_voting_power.value(),
                    )
                )
                .Else(
                    App.globalPut(
                        proposal_against_votes_key,
                        App.globalGet(proposal_against_votes_key)
                        + address_voting_power.value(),
                    )
                ),
                App.localPut(Txn.sender(), proposal_registration_key.value(), Int(1)),
                Approve(),
            )
        ),
        Reject(),
    )


def execute_proposal_program():
    proposal_app_id = Txn.applications[1]
    proposal_registration_key = App.globalGetEx(Int(1), REGISTRATION_ID_KEY)
    registered_proposal_app_id = App.globalGetEx(
        Global.current_application_id(), proposal_registration_key.value()
    )

    proposal_for_votes_key = Concat(
        proposal_registration_key.value(),
        Bytes("_"),
        FOR_VOTES_KEY,
    )

    proposal_against_votes_key = Concat(
        proposal_registration_key.value(),
        Bytes("_"),
        AGAINST_VOTES_KEY,
    )

    for_votes = App.globalGet(proposal_for_votes_key)
    against_votes = App.globalGet(proposal_against_votes_key)

    proposal_can_execute_key = Concat(
        proposal_registration_key.value(),
        Bytes("_"),
        CAN_EXECUTE_KEY,
    )

    can_execute = App.globalGet(proposal_can_execute_key)

    return Seq(
        proposal_registration_key,
        registered_proposal_app_id,
        If(
            And(
                registered_proposal_app_id.value() == proposal_app_id,
                for_votes + against_votes >= App.globalGet(QUORUM_THRESHOLD_KEY),
                for_votes > against_votes,
                can_execute,
                Global.latest_timestamp() > execute_delay_time_end,
            )
        ).Then(
            Seq(
                # app call to proposal target to authorize proposal execution
                # app call to proposal contract to execute
                # app call to proposal target to remove authorization
                App.globalPut(proposal_can_execute_key, Int(0)),
                Approve(),
            )
        ),
        Reject(),
    )


def cancel_proposal_program():
    proposal_app_id = Txn.applications[1]
    proposal_registration_key = App.globalGetEx(Int(1), REGISTRATION_ID_KEY)
    proposal_creator = App.globalGetEx(Int(1), CREATOR_KEY)
    registered_proposal_app_id = App.globalGetEx(
        Global.current_application_id(), proposal_registration_key.value()
    )

    proposal_can_execute_key = Concat(
        proposal_registration_key.value(),
        Bytes("_"),
        CAN_EXECUTE_KEY,
    )

    return Seq(
        proposal_registration_key,
        registered_proposal_app_id,
        proposal_creator,
        If(
            And(
                registered_proposal_app_id.value() == proposal_app_id,
                Or(
                    # governor creator can cancel until the end of execution grace period
                    And(
                        Txn.sender() == App.globalGet(CREATOR_KEY),
                        Global.latest_timestamp() < execute_delay_time_end,
                    ),
                    # proposal creator can cancel until the end of the voting period
                    And(
                        Txn.sender() == proposal_creator.value(),
                        Global.latest_timestamp() < vote_time_end,
                    ),
                ),
            )
        ).Then(
            Seq(
                App.globalPut(proposal_can_execute_key, Int(0)),
                Approve(),
            )
        ),
        Reject(),
    )


def close_out_program():
    address_amount_staked = App.localGetEx(
        Txn.sender(), Global.current_application_id(), ADDRESS_AMOUNT_STAKED_KEY
    )

    return Seq(
        address_amount_staked,
        If(address_amount_staked.hasValue()).Then(
            # if user has staked, they can close out only at the end
            If(validateInTimePeriod(claim_time_start, claim_time_end))
            .Then(
                Seq(
                    sendToken(
                        GOV_TOKEN_KEY, Txn.sender(), address_amount_staked.value()
                    ),
                    Approve(),
                )
            )
            .Else(Reject())
        ),
        # if user has not staked, they can close out at any time
        Approve(),
    )


def approval_program():
    on_create = Seq(
        App.globalPut(CREATOR_KEY, Txn.application_args[0]),
        App.globalPut(GOV_TOKEN_KEY, Btoi(Txn.application_args[1])),
        App.globalPut(PROPOSE_THRESHOLD_KEY, Btoi(Txn.application_args[2])),
        App.globalPut(VOTE_THRESHOLD_KEY, Btoi(Txn.application_args[3])),
        App.globalPut(QUORUM_THRESHOLD_KEY, Btoi(Txn.application_args[4])),
        App.globalPut(STAKE_PERIOD_DURATION_KEY, Btoi(Txn.application_args[5])),
        App.globalPut(PROPOSE_PERIOD_DURATION_KEY, Btoi(Txn.application_args[6])),
        App.globalPut(VOTE_PERIOD_DURATION_KEY, Btoi(Txn.application_args[7])),
        App.globalPut(EXECUTE_DELAY_DURATION_KEY, Btoi(Txn.application_args[8])),
        App.globalPut(CLAIM_PERIOD_DURATION_KEY, Btoi(Txn.application_args[9])),
        App.globalPut(NUM_REGISTERED_PROPOSALS_KEY, Int(0)),
        App.globalPut(MAX_NUM_PROPOSALS_KEY, Int(5)),
        Approve(),
    )

    on_setup = Seq(
        algo_holding,
        start_time_exists,
        # can only set up once
        Assert(algo_holding.value() == Int(0)),
        Assert(Not(start_time_exists.hasValue())),
        optIn(GOV_TOKEN_KEY),
        # kick off the first governance cycle
        App.globalPut(START_TIME_KEY, Global.latest_timestamp()),
        App.globalPut(GOV_CYCLE_ID_KEY, Int(0)),
        Approve(),
    )

    # TODO: potentially unify opt in and stake
    on_opt_in = Return(validateInTimePeriod(stake_time_start, stake_time_end))
    on_stake = stake_program()

    on_delegate_voting_power = (
        If(try_delegate_by_type(ADDRESS_VOTING_POWER_KEY))
        .Then(Approve())
        .Else(Reject())
    )
    on_delegate_proposition_power = (
        If(try_delegate_by_type(ADDRESS_PROPOSITION_POWER_KEY))
        .Then(Approve())
        .Else(Reject())
    )

    on_register_proposal = register_proposal_program()
    on_vote = vote_program()
    on_execute_proposal = execute_proposal_program()
    on_cancel_proposal = cancel_proposal_program()
    on_begin_new_governance_cycle = begin_new_governance_cycle_program()

    on_call_method = Txn.application_args[0]
    on_call = Cond(
        [on_call_method == Bytes("setup"), on_setup],
        [on_call_method == Bytes("stake"), on_stake],
        [on_call_method == Bytes("delegate_voting_power"), on_delegate_voting_power],
        [
            on_call_method == Bytes("delegate_proposition_power"),
            on_delegate_proposition_power,
        ],
        [on_call_method == Bytes("register_proposal"), on_register_proposal],
        [
            on_call_method == Bytes("vote"),
            on_vote,
        ],
        [
            on_call_method == Bytes("execute_proposal"),
            on_execute_proposal,
        ],
        [on_call_method == Bytes("cancel_proposal"), on_cancel_proposal],
        [
            on_call_method == Bytes("begin_new_governance_cycle"),
            on_begin_new_governance_cycle,
        ],
    )

    on_close_out = close_out_program()

    # TODO
    on_delete = Seq(Approve())

    program = Cond(
        [Txn.application_id() == Int(0), on_create],
        [Txn.on_completion() == OnComplete.OptIn, on_opt_in],
        [Txn.on_completion() == OnComplete.NoOp, on_call],
        [Txn.on_completion() == OnComplete.CloseOut, on_close_out],
        [Txn.on_completion() == OnComplete.UpdateApplication, Reject()],
        [Txn.on_completion() == OnComplete.DeleteApplication, on_delete],
    )

    return program


def clear_state_program():
    return Approve()


if __name__ == "__main__":
    with open("governor_approval.teal", "w") as f:
        compiled = compileTeal(approval_program(), mode=Mode.Application, version=5)
        f.write(compiled)

    with open("governor_clear_state.teal", "w") as f:
        compiled = compileTeal(clear_state_program(), mode=Mode.Application, version=5)
        f.write(compiled)
