from gov.contracts.helpers import *
from gov.contracts.config import *

governor_id = Int(1)


def activate_proposal_program():
    # in the future this is where the contract may need to opt into the governor
    # proposal index
    external_registration_id_key = Txn.application_args[1]
    # the app id stored at the governor's proposal index
    external_registration_id_value = App.globalGetEx(
        governor_id, external_registration_id_key
    )

    on_setup = Seq(
        external_registration_id_value,
        Assert(external_registration_id_value.hasValue()),
        Assert(
            external_registration_id_value.value() == Global.current_application_id()
        ),
        App.globalPut(REGISTRATION_ID_KEY, external_registration_id_key),
        Approve(),
    )
    return on_setup


def vote_program():
    authorization_txn_id = Txn.group_index() - Int(1)
    external_registration_id = App.globalGetEx(
        Int(1), App.globalGet(REGISTRATION_ID_KEY)
    )

    address_voting_power = App.localGetEx(
        Txn.sender(), Int(1), ADDRESS_VOTING_POWER_KEY
    )

    vote_value = Btoi(Txn.application_args[1])
    on_vote = Seq(
        address_voting_power,
        external_registration_id,
        Assert(external_registration_id.value() == Global.current_application_id()),
        Assert(
            # verify vote authorization
            And(
                Gtxn[authorization_txn_id].sender() == Txn.sender(),
                Gtxn[authorization_txn_id].type_enum() == TxnType.ApplicationCall,
                Gtxn[authorization_txn_id].application_id()
                == App.globalGet(GOVERNOR_ID_KEY),
                Gtxn[authorization_txn_id].application_args[0]
                == Bytes("authorize_and_burn_vote"),
                # authorization for the current proposal
                Gtxn[authorization_txn_id].applications[1]
                == Global.current_application_id(),
            )
        ),
        Assert(address_voting_power.hasValue()),
        If(vote_value > Int(0))
        .Then(
            App.globalPut(
                FOR_VOTES_KEY,
                App.globalGet(FOR_VOTES_KEY) + address_voting_power.value(),
            )
        )
        .Else(
            App.globalPut(
                FOR_VOTES_KEY,
                App.globalGet(AGAINST_VOTES_KEY) + address_voting_power.value(),
            )
        ),
        Approve(),
    )

    return on_vote


def execute_program():
    on_execute = Seq(
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields(
            {
                TxnField.type_enum: TxnType.Payment,
                TxnField.asset_receiver: App.globalGet(TARGET_ID_KEY),
                TxnField.asset_amount: Int(1000),
            }
        ),
        InnerTxnBuilder.Submit(),
        Approve(),
    )

    return on_execute


def approval_program():

    on_create = Seq(
        App.globalPut(CREATOR_KEY, Txn.accounts[0]),
        App.globalPut(GOVERNOR_ID_KEY, Txn.applications[1]),
        App.globalPut(
            TARGET_ID_KEY, Txn.accounts[1]
        ),  # should be application in the future
        App.globalPut(FOR_VOTES_KEY, Int(0)),
        App.globalPut(AGAINST_VOTES_KEY, Int(0)),
        Approve(),
    )

    on_activate = activate_proposal_program()
    on_vote = vote_program()
    on_execute = execute_program()

    on_call_method = Txn.application_args[0]
    on_call = Seq(
        Cond(
            [on_call_method == Bytes("activate"), on_activate],
            [on_call_method == Bytes("vote"), on_vote],
            [on_call_method == Bytes("execute"), on_execute],
        ),
    )

    on_delete = Approve()

    program = Cond(
        [Txn.application_id() == Int(0), on_create],
        [Txn.on_completion() == OnComplete.NoOp, on_call],
        [Txn.on_completion() == OnComplete.DeleteApplication, on_delete],
        [
            Or(
                Txn.on_completion() == OnComplete.OptIn,
                Txn.on_completion() == OnComplete.CloseOut,
                Txn.on_completion() == OnComplete.UpdateApplication,
            ),
            Reject(),
        ],
    )

    return program


def clear_state_program():
    return Approve()


if __name__ == "__main__":
    with open("amm_approval.teal", "w") as f:
        compiled = compileTeal(approval_program(), mode=Mode.Application, version=5)
        f.write(compiled)

    with open("amm_clear_state.teal", "w") as f:
        compiled = compileTeal(clear_state_program(), mode=Mode.Application, version=5)
        f.write(compiled)
