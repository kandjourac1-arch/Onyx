from enum import Enum
from pydantic import BaseModel
from typing import List

class DomaineEnum(str, Enum):
    VEHICULE = "Vehicule"
    INFORMATIQUE = "Informatique"
    VIVANT = "Vivant"
    PASSIF = "ObjetPassif"

class ModeDeplacement(str, Enum):
    ACTIF = "ACTIF"
    PASSIF = "PASSIF"

class StatutObjet(str, Enum):
    VIABLE = "VIABLE"
    INVIABLE = "INVIABLE"

class MemoContraint(BaseModel):
    objet_principal: str
    domaine: DomaineEnum
    mode: ModeDeplacement
    fonction_touchee: str
    statut_objet: StatutObjet
    solution_validee: List[str]
    cause_rejet: str
    instruction_llm: str