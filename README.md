# Algo-gov

This demo is an on-chain governance contract using smart contracts on the Algorand blockchain. 
This contract allows users to stake their governance tokens, register up to a fixed number of proposals per cycle, vote, and execute approved proposals.

The governance process occurs in time-based cycles. A cycle contains of the following 5 periods, with their respective operations:
#### 1. Staking period
  * Stake
    * Users are able to send their governance tokens to the governor contract to receive governance powers (voting power and proposition power)
    * Once staked, the governance tokens are locked until the claim period
    * Users can only stake once
  * Delegate
    * Users that have already staked are able to delegate their governance powers to another address
      * If a user staked in the previous cycle and has not claimed since then, their voting power and proposition power is reset to their staked amount
    * Voting power and proposition power is delegated separately
    * The delegate address must have power of given type at the moment of delegation
    * Once an address delegates, their power is given to the delegate address in full until the end of the governance cycle
#### 2. Proposition period
  * Register proposal
    * Users that have staked are able to register their proposals with the governor. 
      * If a user staked in the previous cycle and has not claimed since then, their voting power and proposition power is reset to their staked amount
    * A user must have sufficient proposition power, i.e. >= PROPOSE_THRESHOLD
    * There must be free proposal slots remaining
    * If successful, a proposal is assigned a slot in the governor contract and voting will be open in the voting period
    * If successful, user's proposal power will be decreased by PROPOSE_THRESHOLD
  * Cancel proposal
    * The creator of the proposal or the creator of the governor are able to cancel a registered proposal at this stage
#### 3. Voting period
  * Vote
    * Users that have staked are able to vote on proposals
      * If a user staked in the previous cycle and has not claimed since then, their voting power and proposition power is reset to their staked amount
    * A user must have sufficient voting power to participate, as specified by VOTE_THRESHOLD
    * A user cannot vote twice on any given proposal
    * A 0 vote is against, any other vote is for
    * Upon successful vote, the chosen option receives the number of votes equal to user voting power 
  * Cancel proposal
    * The creator of the proposal or the creator of the governor are able to cancel a registered proposal at this stage
#### 4. Execution delay period
  * Cancel proposal
    * The creator of the governor is able to cancel a registered proposal at this stage
#### 5. Claim period
  * Execute proposal
    * Anyone can call execute on the governor to execute a registered proposal
    * To succeed, the proposal must have received total votes above VOTE_THRESHOLD and more votes for than against, and have not been previously cancelled or executed
  * Claim
    * Receive staked tokens (in the future, rewards as well) and opt out of the governance contract
#### 0. Post-claim
  * Begin new governance cycle
    * Anyone can call this to clear out the proposal slots, increment the cycle counter and update start time, kicking off a new cycle

## Usage

The file `gov/operations.py` provides a set of functions that can be used to create and interact
with the governance contract. See that file for documentation.

The file `example.py` demonstrates the governance contract in action.

## ToDo
* Features:
    * Rewards
    * Linked list-based proposal model
* Maintenance
    * Simplify contract code
    * Tests
    * Docs

## Development Setup

This repo requires Python 3.6 or higher. We recommend you use a Python virtual environment to install
the required dependencies.

Set up venv (one time):
 * `python3 -m venv venv`

Active venv:
 * `. venv/bin/activate` (if your shell is bash/zsh)
 * `. venv/bin/activate.fish` (if your shell is fish)

Install dependencies:
* `pip install -r requirements.txt`

Run tests:
* First, start an instance of [sandbox](https://github.com/algorand/sandbox) (requires Docker): `./sandbox up nightly`
* `pytest`
* When finished, the sandbox can be stopped with `./sandbox down`

Format code:
* `black .`
