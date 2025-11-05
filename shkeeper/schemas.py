import datetime
import math
from typing import Annotated, Any, List, Literal, TypeAlias
from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt


# {
#   "address": "TGusXhweqkJ1aJftjmAfLqA1rfEWD4hSGZ",
#   "balance": 165156556,
#   "votes": [
#     {
#       "vote_address": "TJmka325yjJKeFpQDwKSQAoNwEyNGhsaEV",
#       "vote_count": 5759
#     }
#   ],
#   "create_time": 1660833030000,
#   "latest_opration_time": 1752739794000,
#   "allowance": 40860,
#   "latest_withdraw_time": 1752679503000,
#   "latest_consume_time": 1752739794000,
#   "latest_consume_free_time": 1752488991000,
#   "net_window_size": 28800000,
#   "net_window_optimized": true,
#   "account_resource": {
#     "latest_consume_time_for_energy": 1752739794000,
#     "energy_window_size": 28800000,
#     "delegated_frozenV2_balance_for_energy": 3552150,
#     "energy_window_optimized": true
#   },
#   "owner_permission": {
#     "permission_name": "owner",
#     "threshold": 1,
#     "keys": [
#       {
#         "address": "TGusXhweqkJ1aJftjmAfLqA1rfEWD4hSGZ",
#         "weight": 1
#       }
#     ]
#   },
#   "active_permission": [
#     {
#       "type": "Active",
#       "id": 2,
#       "permission_name": "active",
#       "threshold": 1,
#       "operations": "7fff1fc0033e3b00000000000000000000000000000000000000000000000000",
#       "keys": [
#         {
#           "address": "TGusXhweqkJ1aJftjmAfLqA1rfEWD4hSGZ",
#           "weight": 1
#         }
#       ]
#     }
#   ],
#   "frozenV2": [
#     {
#       "amount": 5041000000
#     },
#     {
#       "type": "ENERGY",
#       "amount": 3715447850
#     },
#     {
#       "type": "TRON_POWER"
#     }
#   ],
#   "unfrozenV2": [
#     {
#       "type": "ENERGY",
#       "unfreeze_amount": 1000000,
#       "unfreeze_expire_time": 1752679197000
#     }
#   ],
#   "asset_optimized": true
# }

TronAddress: TypeAlias = str


class TronVote(BaseModel):
    vote_address: TronAddress
    vote_count: PositiveInt


class TronAccountFrozenV2Resource(BaseModel):
    amount: NonNegativeInt = 0
    type: str = "BANDWIDTH"

    def trx(self):
        return self.amount / 1_000_000


class TronAccountUnfrozenV2Resource(BaseModel):
    type: str = "BANDWIDTH"
    unfreeze_amount: NonNegativeInt
    unfreeze_expire_time: datetime.datetime

    def trx(self):
        return self.unfreeze_amount / 1_000_000


class TronAccountAccountResource(BaseModel):
    delegated_frozenV2_balance_for_energy: NonNegativeInt = 0


class TronAccount(BaseModel):
    address: TronAddress
    balance: NonNegativeInt = 0
    allowance: NonNegativeInt = 0
    votes: List[TronVote] = []
    frozenV2: List[TronAccountFrozenV2Resource] = []
    unfrozenV2: List[TronAccountUnfrozenV2Resource] = []
    account_resource: TronAccountAccountResource

    def trx(self):
        return self.balance / 1_000_000

    def has_staked_trx(self):
        for res in self.frozenV2:
            if res.amount > 0:
                return True
        return False


class TronDelegatedResource(BaseModel):
    from_: TronAddress = Field(..., alias="from")
    to: TronAddress
    frozen_balance_for_energy: NonNegativeInt = 0
    frozen_balance_for_bandwidth: NonNegativeInt = 0


class TronAccountResource(BaseModel):
    EnergyLimit: NonNegativeInt = 0
    EnergyUsed: NonNegativeInt = 0
    NetLimit: NonNegativeInt = 0
    NetUsed: NonNegativeInt = 0
    TotalEnergyLimit: NonNegativeInt = 0
    TotalEnergyWeight: NonNegativeInt = 0
    TotalNetLimit: NonNegativeInt = 0
    TotalNetWeight: NonNegativeInt = 0
    freeNetLimit: NonNegativeInt = 0
    freeNetUsed: NonNegativeInt = 0
    tronPowerLimit: NonNegativeInt = 0
    tronPowerUsed: NonNegativeInt = 0

    def available_free_bw(self):
        return self.freeNetLimit - self.freeNetUsed

    def available_staked_bw(self):
        return self.NetLimit - self.NetUsed

    def available_staked_en(self):
        return self.EnergyLimit - self.EnergyUsed


class TronAccountResponse(BaseModel):
    account_info: TronAccount
    delegated_resources: List[TronDelegatedResource]
    account_resource: TronAccountResource

    def estimate_points_from_staking_trx(
        self, trx: int, res_type: Literal["BANDWIDTH", "ENERGY"]
    ):
        if res_type == "ENERGY":
            return math.floor(
                trx
                / self.account_resource.TotalEnergyWeight
                * self.account_resource.TotalEnergyLimit
            )
        elif res_type == "BANDWIDTH":
            return math.floor(
                trx
                / self.account_resource.TotalNetWeight
                * self.account_resource.TotalNetLimit
            )
        else:
            return 0


class TronError(BaseModel):
    status: Literal["error"]
    msg: str
    details: Any
