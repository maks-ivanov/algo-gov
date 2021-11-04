from gov.contracts.helpers import *
from gov.contracts.config import *

governor_id = Int(1)


def activate_proposal_program():
    # in the future this is where the contract may need to opt into the governor
    # for now it just checks that proposal has been successfully registered with the governor,
    # and writes registration id to the state to simplify future opps
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


def execute_program():
    on_execute = Seq(
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields(
            {
                TxnField.type_enum: TxnType.Payment,
                TxnField.receiver: App.globalGet(TARGET_ID_KEY),
                TxnField.amount: Int(1000),
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
        Approve(),
    )

    on_activate = activate_proposal_program()
    on_execute = execute_program()

    on_call_method = Txn.application_args[0]
    on_call = Seq(
        Cond(
            [on_call_method == Bytes("activate"), on_activate],
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
    with open("proposal_approval.teal", "w") as f:
        compiled = compileTeal(approval_program(), mode=Mode.Application, version=5)
        f.write(compiled)

    with open("proposal_clear_state.teal", "w") as f:
        compiled = compileTeal(clear_state_program(), mode=Mode.Application, version=5)
        f.write(compiled)
