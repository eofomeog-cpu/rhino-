"""Read-only access to the original architectural model (meters)."""
import rhino3dm as r
import numpy as np

SRC = "model/Bagneux_Swimming_Pool_Extension.3dm"


class Source:
    def __init__(self, path=SRC):
        self.model = r.File3dm.Read(path)
        self.layers = [l.FullPath for l in self.model.Layers]
        self.objs = list(self.model.Objects)

    def find(self, layer=None, name=None, prefix=None, contains=None):
        out = []
        for o in self.objs:
            lp = self.layers[o.Attributes.LayerIndex]
            n = o.Attributes.Name or ""
            if layer and lp != layer:
                continue
            if name is not None and n != name:
                continue
            if prefix and not n.startswith(prefix):
                continue
            if contains and contains not in n:
                continue
            if o.Geometry.GetBoundingBox().Min.Y > 50:   # stray duplicate massing set
                continue
            out.append(o)
        return out

    def one(self, **kw):
        res = self.find(**kw)
        assert len(res) == 1, (kw, len(res))
        return res[0]


def triangles(obj):
    """All render-mesh triangles of a brep/extrusion as an (n,3,3) array."""
    g = obj.Geometry if hasattr(obj, "Geometry") else obj
    tris = []
    faces = g.Faces if isinstance(g, r.Brep) else []
    for i in range(len(faces)):
        me = faces[i].GetMesh(r.MeshType.Any)
        if me is None:
            continue
        V = [(v.X, v.Y, v.Z) for v in me.Vertices]
        for j in range(len(me.Faces)):
            f = me.Faces[j]
            a, b, c, d = f
            tris.append((V[a], V[b], V[c]))
            if c != d:
                tris.append((V[a], V[c], V[d]))
    return np.array(tris, dtype=float).reshape(-1, 3, 3)


def vertices(obj):
    g = obj.Geometry
    return np.array([(v.Location.X, v.Location.Y, v.Location.Z) for v in g.Vertices])
