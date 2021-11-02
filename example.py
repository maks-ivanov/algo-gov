from time import time, sleep

from algosdk import account, encoding
from algosdk.logic import get_application_address
from gov.operations import (
    createGovernor,
    setupGovernor,
    stake,
    optInToApp,
    sendToken,
    delegateVotingPower,
    createProposal,
    registerProposal,
    activateProposal,
    vote,
)
from gov.util import (
    getBalances,
    getUserLocalState,
    getAppGlobalState,
    getLastBlockTimestamp,
)
from gov.testing.setup import getAlgodClient
from gov.testing.resources import (
    getTemporaryAccount,
    optInToAsset,
    createDummyAsset,
)


def simple_amm():
    client = getAlgodClient()

    print("Alice is generating temporary accounts...")
    creator = getTemporaryAccount(client)
    acct1 = getTemporaryAccount(client)  # voter 1
    acct2 = getTemporaryAccount(client)  # voter 2
    acct3 = getTemporaryAccount(client)  # proposal creator
    acct4 = getTemporaryAccount(client)  # target

    print("Alice is generating example tokens...")
    govTokenAmount = 10 ** 13
    govToken = createDummyAsset(client, govTokenAmount, creator)
    print("Gov token id is:", govToken)
    optInToAsset(client, govToken, acct1)
    print("Alice is creating a governor contract...")
    governorAppId = createGovernor(
        client=client,
        creator=creator,
        govTokenId=govToken,
        proposeThreshold=5,
        voteThreshold=1,
        quorumThreshold=50,
        stakeTimeLengthSeconds=301,
        proposeTimeLengthSeconds=100,
        voteTimeLengthSeconds=100,
        executeDelaySeconds=100,
    )

    print("Jeff is creating a proposal contract...")
    proposalAppId = createProposal(
        client=client, creator=acct3, governorId=governorAppId, targetId=acct4
    )
    print("Proposal id", proposalAppId)
    print(getAppGlobalState(client, proposalAppId))

    setupGovernor(client, governorAppId, creator, govToken)  # 0
    t0 = getLastBlockTimestamp(client)[1]
    print("Alice is staking gov token for votes")
    optInToApp(client, governorAppId, creator)  # 50
    stake(client, governorAppId, 10, creator)  # 100
    sendToken(client, creator, govToken, 1000, acct1)  # 150

    print("Charlie is staking gov token for votes")
    optInToApp(client, governorAppId, acct1)  # 200
    stake(client, governorAppId, 15, acct1)  # 250
    print("Alice's voting info:", getUserLocalState(client, creator))
    print("Charlie's voting info:", getUserLocalState(client, acct1))

    print("Charlie is delegating his votes to Alice")
    print(getLastBlockTimestamp(client)[1] - t0)
    delegateVotingPower(client, governorAppId, acct1, creator)  # 300
    print("Alice's voting info:", getUserLocalState(client, creator))
    print("Charlie's voting info:", getUserLocalState(client, acct1))
    print(getLastBlockTimestamp(client)[1] - t0)


    sleep(3)
    registerProposal(client, governorAppId, proposalAppId, creator)
    print(getLastBlockTimestamp(client)[1] - t0)
    print(getAppGlobalState(client, governorAppId))
    # this points proposal to governor and enables voting
    activateProposal(client, proposalAppId, governorAppId, 0, acct4)
    print(getLastBlockTimestamp(client)[1] - t0)
    print(getAppGlobalState(client, proposalAppId))

    sleep(3)
    vote(client, governorAppId, proposalAppId, 1, creator)
    print(getAppGlobalState(client, proposalAppId))

    # print("Supplying AMM with initial token A and token B")
    # supply(client=client, appID=appID, qA=500_000, qB=100_000_000, supplier=creator)
    # ammBalancesSupplied = getBalances(client, get_application_address(appID))
    # creatorBalancesSupplied = getBalances(client, creator.getAddress())
    # poolTokenFirstAmount = creatorBalancesSupplied[poolToken]
    # print("AMM's balances: ", ammBalancesSupplied)
    # print("Alice's balances: ", creatorBalancesSupplied)
    #
    # print("Supplying AMM with same token A and token B")
    # supply(client=client, appID=appID, qA=100_000, qB=20_000_000, supplier=creator)
    # ammBalancesSupplied = getBalances(client, get_application_address(appID))
    # creatorBalancesSupplied = getBalances(client, creator.getAddress())
    #
    # print("AMM's balances: ", ammBalancesSupplied)
    # print("Alice's balances: ", creatorBalancesSupplied)
    #
    # print("Supplying AMM with too large ratio of token A and token B")
    # supply(client=client, appID=appID, qA=100_000, qB=100_000, supplier=creator)
    # ammBalancesSupplied = getBalances(client, get_application_address(appID))
    # creatorBalancesSupplied = getBalances(client, creator.getAddress())
    # print("AMM's balances: ", ammBalancesSupplied)
    # print("Alice's balances: ", creatorBalancesSupplied)
    #
    # print("Supplying AMM with too small ratio of token A and token B")
    # supply(client=client, appID=appID, qA=100_000, qB=100_000_000, supplier=creator)
    # ammBalancesSupplied = getBalances(client, get_application_address(appID))
    # creatorBalancesSupplied = getBalances(client, creator.getAddress())
    #
    # print("AMM's balances: ", ammBalancesSupplied)
    # print("Alice's balances: ", creatorBalancesSupplied)
    # poolTokenTotalAmount = creatorBalancesSupplied[poolToken]
    # print(" ")
    # print("Alice is exchanging her Token A for Token B")
    # marketSwap(client=client, appID=appID, tokenId=govToken, amount=1_000, trader=creator)
    # ammBalancesTraded = getBalances(client, get_application_address(appID))
    # creatorBalancesTraded = getBalances(client, creator.getAddress())
    # print("AMM's balances: ", ammBalancesTraded)
    # print("Alice's balances: ", creatorBalancesTraded)
    #
    # print("Alice is exchanging her Token B for Token A")
    # marketSwap(
    #     client=client,
    #     appID=appID,
    #     tokenId=tokenB,
    #     amount=int(1_000_000 * 1.003),
    #     trader=creator,
    # )
    # ammBalancesTraded = getBalances(client, get_application_address(appID))
    # creatorBalancesTraded = getBalances(client, creator.getAddress())
    # print("AMM's balances: ", ammBalancesTraded)
    # print("Alice's balances: ", creatorBalancesTraded)
    # print(" ")
    #
    # print("Withdrawing first supplied liquidity from AMM")
    # print("Withdrawing: ", poolTokenFirstAmount)
    # withdraw(
    #     client=client,
    #     appID=appID,
    #     poolTokenAmount=poolTokenFirstAmount,
    #     withdrawAccount=creator,
    # )
    # ammBalancesWithdrawn = getBalances(client, get_application_address(appID))
    # print("AMM's balances: ", ammBalancesWithdrawn)
    #
    # print("Withdrawing remainder of the supplied liquidity from AMM")
    # poolTokenTotalAmount -= poolTokenFirstAmount
    # withdraw(
    #     client=client,
    #     appID=appID,
    #     poolTokenAmount=poolTokenTotalAmount,
    #     withdrawAccount=creator,
    # )
    # ammBalancesWithdrawn = getBalances(client, get_application_address(appID))
    # print("AMM's balances: ", ammBalancesWithdrawn)
    # print("Closing AMM")
    # closeAmm(client=client, appID=appID, closer=creator)


simple_amm()
