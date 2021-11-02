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
    getBalances,
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

    # 7 params + creation time + num active proposals + 5 proposals
    globalSchema = transaction.StateSchema(num_uints=7 + 2 + 5, num_byte_slices=1)
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
    """Finish setting up an amm.

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

    # bytes: creator, target, registration id; uints: governor, for, against, cancelled
    globalSchema = transaction.StateSchema(num_uints=4, num_byte_slices=3)
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
    funder: Account,
) -> int:

    appAddr = get_application_address(proposalAppId)

    suggestedParams = client.suggested_params()

    fundingAmount = 100000 + 1000 * 2

    fundAppTxn = transaction.PaymentTxn(
        sender=funder.getAddress(),
        receiver=appAddr,
        amt=fundingAmount,
        sp=suggestedParams,
    )

    appCallTxn = transaction.ApplicationCallTxn(
        sender=funder.getAddress(),
        index=proposalAppId,
        on_complete=transaction.OnComplete.NoOpOC,
        app_args=[b"activate", registrationId.to_bytes(8, "big")],
        foreign_apps=[governorAppId],
        sp=suggestedParams,
    )

    transaction.assign_group_id([fundAppTxn, appCallTxn])

    signedFundAppTxn = fundAppTxn.sign(funder.getPrivateKey())
    signedSetupTxn = appCallTxn.sign(funder.getPrivateKey())

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
        app_args=["authorize_and_burn_vote"],
        foreign_apps=[proposalAppId],
        sp=suggestedParams,
    )

    voteCallTxn = transaction.ApplicationCallTxn(
        sender=account.getAddress(),
        index=proposalAppId,
        on_complete=transaction.OnComplete.NoOpOC,
        app_args=["vote", proposalVote.to_bytes(8, "big")],
        foreign_apps=[governorAppId],
        sp=suggestedParams,
    )

    transaction.assign_group_id([authCallTxn, voteCallTxn])

    signedAuthTxn = authCallTxn.sign(account.getPrivateKey())
    signedVoteTxn = voteCallTxn.sign(account.getPrivateKey())

    client.send_transactions([signedAuthTxn, signedVoteTxn])
    waitForTransaction(client, signedVoteTxn.get_txid())


def claim(client: AlgodClient, appID: int, amount: int, account: Account) -> None:
    pass


def supply(
    client: AlgodClient, appID: int, qA: int, qB: int, supplier: Account
) -> None:
    """Supply liquidity to the pool.
    Let rA, rB denote the existing pool reserves of token A and token B respectively

    First supplier will receive sqrt(qA*qB) tokens, subsequent suppliers will receive
    qA/rA where rA is the amount of token A already in the pool.
    If qA/qB != rA/rB, the pool will first attempt to take full amount qA, returning excess token B
    Else if there is insufficient amount qB, the pool will then attempt to take the full amount qB, returning
     excess token A
    Else transaction will be rejected

    Args:
        client: AlgodClient,
        appID: amm app id,
        qA: amount of token A to supply the pool
        qB: amount of token B to supply to the pool
        supplier: supplier account
    """
    assertSetup(client, appID)
    appAddr = get_application_address(appID)
    appGlobalState = getAppGlobalState(client, appID)
    suggestedParams = client.suggested_params()

    tokenA = appGlobalState[b"token_a_key"]
    tokenB = appGlobalState[b"token_b_key"]
    poolToken = getPoolTokenId(appGlobalState)

    # pay for the fee incurred by AMM for sending back the pool token
    feeTxn = transaction.PaymentTxn(
        sender=supplier.getAddress(),
        receiver=appAddr,
        amt=2_000,
        sp=suggestedParams,
    )

    tokenATxn = transaction.AssetTransferTxn(
        sender=supplier.getAddress(),
        receiver=appAddr,
        index=tokenA,
        amt=qA,
        sp=suggestedParams,
    )
    tokenBTxn = transaction.AssetTransferTxn(
        sender=supplier.getAddress(),
        receiver=appAddr,
        index=tokenB,
        amt=qB,
        sp=suggestedParams,
    )

    appCallTxn = transaction.ApplicationCallTxn(
        sender=supplier.getAddress(),
        index=appID,
        on_complete=transaction.OnComplete.NoOpOC,
        app_args=[b"supply"],
        foreign_assets=[tokenA, tokenB, poolToken],
        sp=suggestedParams,
    )

    transaction.assign_group_id([feeTxn, tokenATxn, tokenBTxn, appCallTxn])
    signedFeeTxn = feeTxn.sign(supplier.getPrivateKey())
    signedTokenATxn = tokenATxn.sign(supplier.getPrivateKey())
    signedTokenBTxn = tokenBTxn.sign(supplier.getPrivateKey())
    signedAppCallTxn = appCallTxn.sign(supplier.getPrivateKey())

    client.send_transactions(
        [signedFeeTxn, signedTokenATxn, signedTokenBTxn, signedAppCallTxn]
    )
    waitForTransaction(client, signedAppCallTxn.get_txid())


def withdraw(
    client: AlgodClient, appID: int, poolTokenAmount: int, withdrawAccount: Account
) -> None:
    """Withdraw liquidity  + rewards from the pool back to supplier.
    Supplier should receive tokenA, tokenB + fees proportional to the liquidity share in the pool they choose to withdraw.

    Args:
        client: AlgodClient,
        appID: amm app id,
        poolTokenAmount: pool token quantity,
        withdrawAccount: supplier account,
    """
    assertSetup(client, appID)
    appAddr = get_application_address(appID)
    appGlobalState = getAppGlobalState(client, appID)
    suggestedParams = client.suggested_params()

    # pay for the fee incurred by AMM for sending back tokens A and B
    feeTxn = transaction.PaymentTxn(
        sender=withdrawAccount.getAddress(),
        receiver=appAddr,
        amt=2_000,
        sp=suggestedParams,
    )

    tokenA = appGlobalState[b"token_a_key"]
    tokenB = appGlobalState[b"token_b_key"]
    poolToken = getPoolTokenId(appGlobalState)

    poolTokenTxn = transaction.AssetTransferTxn(
        sender=withdrawAccount.getAddress(),
        receiver=appAddr,
        index=poolToken,
        amt=poolTokenAmount,
        sp=suggestedParams,
    )

    appCallTxn = transaction.ApplicationCallTxn(
        sender=withdrawAccount.getAddress(),
        index=appID,
        on_complete=transaction.OnComplete.NoOpOC,
        app_args=[b"withdraw"],
        foreign_assets=[tokenA, tokenB, poolToken],
        sp=suggestedParams,
    )

    transaction.assign_group_id([feeTxn, poolTokenTxn, appCallTxn])
    signedFeeTxn = feeTxn.sign(withdrawAccount.getPrivateKey())
    signedPoolTokenTxn = poolTokenTxn.sign(withdrawAccount.getPrivateKey())
    signedAppCallTxn = appCallTxn.sign(withdrawAccount.getPrivateKey())

    client.send_transactions([signedFeeTxn, signedPoolTokenTxn, signedAppCallTxn])
    waitForTransaction(client, signedAppCallTxn.get_txid())


def marketSwap(
    client: AlgodClient, appID: int, tokenId: int, amount: int, trader: Account
):
    """Swap tokenId token for the other token in the pool
    This action can only happen if there is liquidity in the pool
    A fee (in bps, configured on app creation) is taken out of the input amount before calculating the output amount
    """
    limitSwap(client, appID, tokenId, amount, 0, trader)


def limitSwap(
    client: AlgodClient,
    appID: int,
    tokenId: int,
    amount: int,
    minOtherAmount: int,
    trader: Account,
):
    """Swap tokenId token for the other token in the pool.
    Perform the swap only if the other token amount received by the trader is >= minOtherAmount
    This action can only happen if there is liquidity in the pool
    A fee (in bps, configured on app creation) is taken out of the input amount before calculating the output amount
    """
    assertSetup(client, appID)
    appAddr = get_application_address(appID)
    appGlobalState = getAppGlobalState(client, appID)
    suggestedParams = client.suggested_params()

    feeTxn = transaction.PaymentTxn(
        sender=trader.getAddress(),
        receiver=appAddr,
        amt=1000,
        sp=suggestedParams,
    )

    tokenA = appGlobalState[b"token_a_key"]
    tokenB = appGlobalState[b"token_b_key"]

    tradeTxn = transaction.AssetTransferTxn(
        sender=trader.getAddress(),
        receiver=appAddr,
        index=tokenId,
        amt=amount,
        sp=suggestedParams,
    )

    appCallTxn = transaction.ApplicationCallTxn(
        sender=trader.getAddress(),
        index=appID,
        on_complete=transaction.OnComplete.NoOpOC,
        app_args=[b"swap", minOtherAmount.to_bytes(8, "big")],
        foreign_assets=[tokenA, tokenB],
        sp=suggestedParams,
    )

    transaction.assign_group_id([feeTxn, tradeTxn, appCallTxn])
    signedFeeTxn = feeTxn.sign(trader.getPrivateKey())
    signedTradeTxn = tradeTxn.sign(trader.getPrivateKey())
    signedAppCallTxn = appCallTxn.sign(trader.getPrivateKey())

    client.send_transactions([signedFeeTxn, signedTradeTxn, signedAppCallTxn])
    waitForTransaction(client, signedAppCallTxn.get_txid())


def closeAmm(client: AlgodClient, appID: int, closer: Account):
    """Close an amm.

    This action can only happen if there is no liquidity in the pool (outstanding pool tokens = 0).

    Args:
        client: An Algod client.
        appID: The app ID of the amm.
        closer: closer account. Must be the original creator of the pool.
    """

    deleteTxn = transaction.ApplicationDeleteTxn(
        sender=closer.getAddress(),
        index=appID,
        sp=client.suggested_params(),
    )
    signedDeleteTxn = deleteTxn.sign(closer.getPrivateKey())

    client.send_transaction(signedDeleteTxn)

    waitForTransaction(client, signedDeleteTxn.get_txid())


def getPoolTokenId(appGlobalState):
    try:
        return appGlobalState[b"pool_token_key"]
    except KeyError:
        raise RuntimeError(
            "Pool token id doesn't exist. Make sure the app has been set up"
        )


def assertSetup(client: AlgodClient, appID: int) -> None:
    balances = getBalances(client, get_application_address(appID))
    assert (
        balances[0] >= MIN_BALANCE_REQUIREMENT
    ), "AMM must be set up and funded first. AMM balances: " + str(balances)


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
