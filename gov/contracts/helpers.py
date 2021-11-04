from pyteal import *

from gov.contracts.config import FOR_VOTES_KEY, AGAINST_VOTES_KEY, CAN_EXECUTE_KEY


@Subroutine(TealType.uint64)
def validateTokenReceived(
    transaction_index: TealType.uint64, token_key: TealType.bytes
) -> Expr:
    return And(
        Gtxn[transaction_index].type_enum() == TxnType.AssetTransfer,
        Gtxn[transaction_index].sender() == Txn.sender(),
        Gtxn[transaction_index].asset_receiver()
        == Global.current_application_address(),
        Gtxn[transaction_index].xfer_asset() == App.globalGet(token_key),
        Gtxn[transaction_index].asset_amount() > Int(0),
    )


@Subroutine(TealType.uint64)
def validateInTimePeriod(
    beginTimeStampInclusive: TealType.uint64, endTimeExclusive: TealType.uint64
) -> Expr:
    current_timestamp = Global.latest_timestamp()
    return And(
        current_timestamp >= beginTimeStampInclusive,
        current_timestamp < endTimeExclusive,
    )


@Subroutine(TealType.none)
def register_proposal(registration_slot: TealType.uint64):
    return Seq(
        App.globalPut(Itob(registration_slot), Txn.applications[1]),
        App.globalPut(
            Concat(Itob(registration_slot), Bytes("_"), FOR_VOTES_KEY), Int(0)
        ),
        App.globalPut(
            Concat(Itob(registration_slot), Bytes("_"), AGAINST_VOTES_KEY),
            Int(0),
        ),
        App.globalPut(
            Concat(Itob(registration_slot), Bytes("_"), CAN_EXECUTE_KEY),
            Int(1),
        ),
    )


@Subroutine(TealType.none)
def unregister_proposal(registration_slot: TealType.uint64):
    return Seq(
        App.globalDel(Itob(registration_slot)),
        App.globalDel(Concat(Itob(registration_slot), Bytes("_"), FOR_VOTES_KEY)),
        App.globalDel(
            Concat(Itob(registration_slot), Bytes("_"), AGAINST_VOTES_KEY),
        ),
        App.globalDel(
            Concat(Itob(registration_slot), Bytes("_"), CAN_EXECUTE_KEY),
        ),
    )


@Subroutine(TealType.none)
def sendToken(
    token_key: TealType.bytes, receiver: TealType.bytes, amount: TealType.uint64
) -> Expr:
    return Seq(
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields(
            {
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.xfer_asset: App.globalGet(token_key),
                TxnField.asset_receiver: receiver,
                TxnField.asset_amount: amount,
            }
        ),
        InnerTxnBuilder.Submit(),
    )


@Subroutine(TealType.none)
def optIn(token_key: TealType.bytes) -> Expr:
    return sendToken(token_key, Global.current_application_address(), Int(0))
