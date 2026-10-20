"""Add plane/pour zones to the routed board, fill them, save."""
import sys
import pcbnew
import gen_pcb

src, dst = sys.argv[1], sys.argv[2]
board = pcbnew.LoadBoard(src)
gen_pcb.zones_only = True
W, H = gen_pcb.place.W, gen_pcb.place.H
MM = pcbnew.FromMM
nets = board.GetNetsByName()


def zone(layer, net, clr, full=False):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(nets[net])
    ol = z.Outline()
    ol.NewOutline()
    for x, y in [(0.3, 0.3), (W - 0.3, 0.3), (W - 0.3, H - 0.3), (0.3, H - 0.3)]:
        ol.Append(MM(x), MM(y))
    z.SetLocalClearance(MM(clr))
    z.SetMinThickness(MM(0.2))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL if full else pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(MM(0.3))
    z.SetThermalReliefSpokeWidth(MM(0.4))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    board.Add(z)


zone(pcbnew.In1_Cu, 'GND', 0.2)
zone(pcbnew.In2_Cu, '+3V3', 0.2)
zone(pcbnew.F_Cu, 'GND', 0.2, full=True)
zone(pcbnew.B_Cu, 'GND', 0.2, full=True)
board.BuildConnectivity()
pcbnew.ZONE_FILLER(board).Fill(board.Zones())
pcbnew.SaveBoard(dst, board)
print('poured ->', dst)
