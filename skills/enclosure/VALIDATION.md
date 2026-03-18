# Validation Rules

## Parameters
L: float
W: float
H: float
T: float = 2
PR: float = 3
lid_type: str = screw

## Checks

### Body count
- total_bodies: 2

### EnclosureBase
- exists: true
- bbox: L, W, H (tolerance 0.5)
- bbox_position: 0, H (tolerance 0.5)
- solid_count: 1
- valid_solid: true

#### when lid_type == "screw"
- volume: L*W*H - (L-2*T)*(W-2*T)*(H-T) + 4*3.14159*PR**2*(H-T) (tolerance 5%)
- min_children: 4

#### when lid_type == "press-fit"
- volume: L*W*H - (L-2*T)*(W-2*T)*(H-T) (tolerance 5%)

#### when lid_type == "snap-fit"
- volume: L*W*H - (L-2*T)*(W-2*T)*(H-T) (tolerance 5%)

### EnclosureLid
- exists: true
- solid_count: 1
- valid_solid: true

#### when lid_type == "screw"
- bbox: L, W, T (tolerance 0.5)
- bbox_position: H, H+T (tolerance 0.5)
- has_holes: 4

#### when lid_type == "press-fit"
- bbox: L, W, T+3 (tolerance 0.5)
- bbox_position: H-3, H+T (tolerance 0.5)
- section_area: Z, H-1, (L-2*T-0.4)*(W-2*T-0.4) (tolerance 10%)

#### when lid_type == "snap-fit"
- bbox: L, W, T+3 (tolerance 0.5)
- bbox_position: H-3, H+T (tolerance 0.5)
- section_area: Z, H-1, (L-2*T-2)*(W-2*T-2) (tolerance 10%)
