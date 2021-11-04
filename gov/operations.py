from typing import Tuple

from algosdk.v2client.algod import AlgodClient
from algosdk.future import transaction
from algosdk.logic import get_application_address
from algosdk import encoding

from .account import Account
from gov.contracts import Governor, Proposal
from .util import (
    waitForTransaction,
    fullyCompileContract,
    getAppGlobalState,
)

GOVERNOR_APPROVAL_PROGRAM = b""
GOVERNOR_CLEAR_STATE_PROGRAM = b""

PROPOSAL_APPROVAL_PROGRAM = b""
PROPOSAL_CLEAR_STATE_PROGRAM = b""

MIN_BALANCE_REQUIREMENT = (
    # min account balance
    100_000
    # additional min balance for 1 asset
    + 100_000
)


def getGovernorContracts(client: AlgodClient) -> Tuple[bytes, bytes]:
    """Get the compiled TEAL contracts for the amm.

    Args:q
        client: An algod client that has the ability to compile TEAL programs.

    Returns:
        A tuple of 2 byte strings. The first is the approval program, and the
        second is the clear state program.
    """
    global GOVERNOR_APPROVAL_PROGRAM
    global GOVERNOR_CLEAR_STATE_PROGRAM

    if len(GOVERNOR_APPROVAL_PROGRAM) == 0:
        GOVERNOR_APPROVAL_PROGRAM = fullyCompileContract(
            client, Governor.approval_program()
        )
        GOVERNOR_CLEAR_STATE_PROGRAM = fullyCompileContract(
            client, Governor.clear_state_program()
        )

    return GOVERNOR_APPROVAL_PROGRAM, GOVERNOR_CLEAR_STATE_PROGRAM


# this is mainly for testing as it only creates one specific type of proposal defined in Proposal.py
def getProposalContracts(client: AlgodClient) -> Tuple[bytes, bytes]:
    """Get the compiled TEAL contracts for the amm.

    Args:q
        client: An algod client that has the ability to compile TEAL programs.

    Returns:
        A tuple of 2 byte strings. The first is the approval program, and the
        second is the clear state program.
    """
    global PROPOSAL_APPROVAL_PROGRAM
    global PROPOSAL_CLEAR_STATE_PROGRAM

    if len(PROPOSAL_APPROVAL_PROGRAM) == 0:
        PROPOSAL_APPROVAL_PROGRAM = fullyCompileContract(
            client, Proposal.approval_program()
        )
        PROPOSAL_CLEAR_STATE_PROGRAM = fullyCompileContract(
            client, Proposal.clear_state_program()
        )

    return PROPOSAL_APPROVAL_PROGRAM, PROPOSAL_CLEAR_STATE_PROGRAM


def createGovernor(
    client: AlgodClient,
    creator: Account,
    govTokenId: int,
    proposeThreshold: int,
    voteThreshold: int,
    quorumThreshold: int,
    stakeTimeLengthSeconds: int,
    proposeTimeLengthSeconds: int,
    voteTimeLengthSeconds: int,
    executeDelaySeconds: int,
) -> int:
    """Create a new amm.

    Args:
        client: An algod client.
        creator: The account that will create the governor application.Governor.py
        govTokenId: The id of governance token
        proposeThreshold: minimum voting power required to create a proposal
        voteThreshold: minimum voting power required to vote on a proposal
        quorumThreshold: minimum votes cast to pass a proposal
        stakeTimeLengthSeconds: the time length of staking and delegation period
        proposeTimeLength: the time length of propose period
        voteTimeLengthSeconds: the time length of voting period
        executeDelaySeconds: the time length of the period between proposal approval and execution

    Returns:
        The ID of the newly created app.
    """
    approval, clear = getGovernorContracts(client)

    # 7 params + creation time + num active proposals + 5 proposal slots with for, against, and can_execute
    globalSchema = transaction.StateSchema(num_uints=7 + 2 + 5 * 4, num_byte_slices=1)
    # tokens committed, voting power, proposal power, proposals voted
    localSchema = transaction.StateSchema(num_uints=3 + 5, num_byte_slices=0)

    app_args = [
        encoding.decode_address(creator.getAddress()),
        govTokenId.to_bytes(8, "big"),
        proposeThreshold.to_bytes(8, "big"),
        voteThreshold.to_bytes(8, "big"),
        quorumThreshold.to_bytes(8, "big"),
        stakeTimeLengthSeconds.to_bytes(8, "big"),
        proposeTimeLengthSeconds.to_bytes(8, "big"),
        voteTimeLengthSeconds.to_bytes(8, "big"),
        executeDelaySeconds.to_bytes(8, "big"),
    ]

    txn = transaction.ApplicationCreateTxn(
        sender=creator.getAddress(),
        on_complete=transaction.OnComplete.NoOpOC,
        approval_program=approval,
        clear_program=clear,
        global_schema=globalSchema,
        local_schema=localSchema,
        app_args=app_args,
        sp=client.suggested_params(),
    )

    signedTxn = txn.sign(creator.getPrivateKey())

    client.send_transaction(signedTxn)

    response = waitForTransaction(client, signedTxn.get_txid())
    assert response.applicationIndex is not None and response.applicationIndex > 0
    return response.applicationIndex


def setupGovernor(
    client: AlgodClient, appID: int, funder: Account, govTokenId: int
) -> int:
    """Finish setting up a governor contract.

    This operation funds the pool account, creates pool token,
    and opts app into tokens A and B, all in one atomic transaction group.

    Args:
        client: An algod client.
        appID: The app ID of the amm.
        funder: The account providing the funding for the escrow account.
        govTokenId: governance token id.
    """
    appAddr = get_application_address(appID)

    suggestedParams = client.suggested_params()

    fundingAmount = (
        MIN_BALANCE_REQUIREMENT
        # additional balance to opt into and send governance token
        + 1_000
    )

    fundAppTxn = transaction.PaymentTxn(
        sender=funder.getAddress(),
        receiver=appAddr,
        amt=fundingAmount,
        sp=suggestedParams,
    )

    setupTxn = transaction.ApplicationCallTxn(
        sender=funder.getAddress(),
        index=appID,
        on_complete=transaction.OnComplete.NoOpOC,
        app_args=[b"setup"],
        foreign_assets=[govTokenId],
        sp=suggestedParams,
    )

    transaction.assign_group_id([fundAppTxn, setupTxn])

    signedFundAppTxn = fundAppTxn.sign(funder.getPrivateKey())
    signedSetupTxn = setupTxn.sign(funder.getPrivateKey())

    client.send_transactions([signedFundAppTxn, signedSetupTxn])

    waitForTransaction(client, signedFundAppTxn.get_txid())


def optInToApp(client: AlgodClient, appID: int, account: Account) -> None:
    suggestedParams = client.suggested_params()

    optInTxn = transaction.ApplicationOptInTxn(
        sender=account.getAddress(), sp=suggestedParams, index=appID
    )

    signedOptInTxn = optInTxn.sign(account.getPrivateKey())
    client.send_transaction(signedOptInTxn)
    waitForTransaction(client, signedOptInTxn.get_txid())


def stake(client: AlgodClient, appID: int, amount: int, account: Account) -> None:

    appAddr = get_application_address(appID)
    suggestedParams = client.suggested_params()
    appGlobalState = getAppGlobalState(client, appID)
    govToken = appGlobalState[b"gov_token_key"]

    govTokenTxn = transaction.AssetTransferTxn(
        sender=account.getAddress(),
        receiver=appAddr,
        index=govToken,
        amt=amount,
        sp=suggestedParams,
    )

    appCallTxn = transaction.ApplicationCallTxn(
        sender=account.getAddress(),
        index=appID,
        on_complete=transaction.OnComplete.NoOpOC,
        app_args=[b"stake"],
        foreign_assets=[govToken],
        sp=suggestedParams,
    )

    transaction.assign_group_id([govTokenTxn, appCallTxn])
    signedGovTokenTxn = govTokenTxn.sign(account.getPrivateKey())
    signedAppCallTxn = appCallTxn.sign(account.getPrivateKey())

    client.send_transactions([signedGovTokenTxn, signedAppCallTxn])
    waitForTransaction(client, signedAppCallTxn.get_txid())


def delegateVotingPower(
    client: AlgodClient, appID: int, account: Account, delegateTo: Account
) -> None:
    suggestedParams = client.suggested_params()

    appCallTxn = transaction.ApplicationCallTxn(
        sender=account.getAddress(),
        index=appID,
        on_complete=transaction.OnComplete.NoOpOC,
        accounts=[delegateTo.getAddress()],
        app_args=[b"delegate_voting_power"],
        sp=suggestedParams,
    )

    signedAppCallTxn = appCallTxn.sign(account.getPrivateKey())

    client.send_transaction(signedAppCallTxn)

    waitForTransaction(client, signedAppCallTxn.get_txid())


def createProposal(
    client: AlgodClient,
    creator: Account,
    governorId: int,
    targetId: Account,  # account for now, should be application in the future
) -> None:
    approval, clear = getProposalContracts(client)

    # bytes: creator, target, registration id; uints: governor
    globalSchema = transaction.StateSchema(num_uints=1, num_byte_slices=3)
    # tokens committed, voting power, proposal power, proposals voted
    localSchema = transaction.StateSchema(num_uints=0, num_byte_slices=0)

    txn = transaction.ApplicationCreateTxn(
        sender=creator.getAddress(),
        on_complete=transaction.OnComplete.NoOpOC,
        approval_program=approval,
        clear_program=clear,
        global_schema=globalSchema,
        local_schema=localSchema,
        foreign_apps=[governorId],
        accounts=[targetId.getAddress()],
        sp=client.suggested_params(),
    )

    signedTxn = txn.sign(creator.getPrivateKey())

    client.send_transaction(signedTxn)

    response = waitForTransaction(client, signedTxn.get_txid())
    assert response.applicationIndex is not None and response.applicationIndex > 0
    return response.applicationIndex


def registerProposal(
    client: AlgodClient,
    governorAppId: int,
    proposalAppId: int,
    account: Account,
) -> None:
    suggestedParams = client.suggested_params()

    appCallTxn = transaction.ApplicationCallTxn(
        sender=account.getAddress(),
        index=governorAppId,
        on_complete=transaction.OnComplete.NoOpOC,
        app_args=[b"register_proposal"],
        foreign_apps=[proposalAppId],
        sp=suggestedParams,
    )

    signedAppCallTxn = appCallTxn.sign(account.getPrivateKey())

    client.send_transaction(signedAppCallTxn)

    waitForTransaction(client, signedAppCallTxn.get_txid())


def activateProposal(
    client: AlgodClient,
    proposalAppId: int,
    governorAppId: int,
    registrationId: int,
    account: Account,
) -> int:

    appAddr = get_application_address(proposalAppId)

    suggestedParams = client.suggested_params()

    fundingAmount = 100000 + 1000 * 2

    fundAppTxn = transaction.PaymentTxn(
        sender=account.getAddress(),
        receiver=appAddr,
        amt=fundingAmount,
        sp=suggestedParams,
    )

    appCallTxn = transaction.ApplicationCallTxn(
        sender=account.getAddress(),
        index=proposalAppId,
        on_complete=transaction.OnComplete.NoOpOC,
        app_args=[b"activate", registrationId.to_bytes(8, "big")],
        foreign_apps=[governorAppId],
        sp=suggestedParams,
    )

    transaction.assign_group_id([fundAppTxn, appCallTxn])

    signedFundAppTxn = fundAppTxn.sign(account.getPrivateKey())
    signedSetupTxn = appCallTxn.sign(account.getPrivateKey())

    client.send_transactions([signedFundAppTxn, signedSetupTxn])

    waitForTransaction(client, signedFundAppTxn.get_txid())


def vote(
    client: AlgodClient,
    governorAppId: int,
    proposalAppId: int,
    proposalVote: int,
    account: Account,
) -> None:

    suggestedParams = client.suggested_params()

    authCallTxn = transaction.ApplicationCallTxn(
        sender=account.getAddress(),
        index=governorAppId,
        on_complete=transaction.OnComplete.NoOpOC,
        app_args=[b"vote", proposalVote.to_bytes(8, "big")],
        foreign_apps=[proposalAppId],
        sp=suggestedParams,
    )

    signedAuthTxn = authCallTxn.sign(account.getPrivateKey())
    client.send_transaction(signedAuthTxn)
    waitForTransaction(client, signedAuthTxn.get_txid())


def executeProposal(
    client: AlgodClient,
    governorAppId: int,
    proposalAppId: int,
    account: Account,
) -> None:

    suggestedParams = client.suggested_params()

    authCallTxn = transaction.ApplicationCallTxn(
        sender=account.getAddress(),
        index=governorAppId,
        on_complete=transaction.OnComplete.NoOpOC,
        app_args=[b"execute_proposal"],
        foreign_apps=[proposalAppId],
        sp=suggestedParams,
    )

    # in the future the below transaction will be deprecated,
    # as the governor will be able to call execute on the proposal contract directly
    target = encoding.encode_address(
        getAppGlobalState(client, proposalAppId)[b"target_id_key"]
    )

    # print(account.getAddress())
    execCallTxn = transaction.ApplicationCallTxn(
        sender=account.getAddress(),
        index=proposalAppId,
        on_complete=transaction.OnComplete.NoOpOC,
        app_args=[b"execute"],
        accounts=[target],
        sp=suggestedParams,
    )

    transaction.assign_group_id([authCallTxn, execCallTxn])

    signedAuthTxn = authCallTxn.sign(account.getPrivateKey())
    signedExecTxn = execCallTxn.sign(account.getPrivateKey())

    client.send_transactions([signedAuthTxn, signedExecTxn])
    waitForTransaction(client, signedExecTxn.get_txid())


def claim(client: AlgodClient, appID: int, account: Account) -> None:
    pass


def sendToken(
    client: AlgodClient, sender: Account, tokenId: int, amount: int, receiver: Account
):
    suggestedParams = client.suggested_params()

    transferTxn = transaction.AssetTransferTxn(
        sender=sender.getAddress(),
        receiver=receiver.getAddress(),
        index=tokenId,
        amt=amount,
        sp=suggestedParams,
    )

    signedTransferTxn = transferTxn.sign(sender.getPrivateKey())

    client.send_transaction(signedTransferTxn)
    waitForTransaction(client, signedTransferTxn.get_txid())
