'''
Tools work with geographical data
'''

import os, time
import pysal as ps
import numpy as np
import pandas as pd
import multiprocessing as mp
from scipy.spatial.distance import cdist
try:
    from ogr import osr
except:
    print ("WARNING: GDAL (and ogr) are not installed. This may create",
            "some methods to not work")
 

def clip_shp(shp_in, col_name, keys, shp_out=None):
    '''
    Clip out part of a shapefile based on a subset of one of the dbf columns.
    ...

    Arguments
    =========
    shp_in      : str
                  Path to the shapefile to be clipped
    col_name    : str
                  Name of the column to subset
    keys        : list
                  Values of 'col' to be clipped out of shp_in and written into
                  shp_out.
    shp_out     : str
                  [Optional] Path to the shapefile to be created. If None,
                  writes the file with the same name plus '_clipped' appended.
    Returns
    =======
    shp_out     : str
                  [Optional] Path to the shapefile to be created. If None,
                  writes the file with the same name plus '_clipped' appended.
    '''
    t0 = time.clock()
    k = list(set(keys))
    if len(k) != len(keys):
        raise Exception, "Please don't pass duplicates in keys"
    keys = k
    if not shp_out:
        shp_out = shp_in[:-4] + '_clipped.shp'
    dbi = ps.open(shp_in[:-3] + 'dbf')
    dbo = ps.open(shp_out[:-3] + 'dbf', 'w')
    dbo.header = dbi.header
    dbo.field_spec = dbi.field_spec
    shpi = ps.open(shp_in)
    shpo = ps.open(shp_out, 'w')
    col = np.array(dbi.by_col(col_name))
    full = pd.DataFrame({'full': np.array(dbi.by_col(col_name))})
    subset = pd.DataFrame({'sub': keys}, index=keys)
    to_clip = full.join(subset, on='full').dropna().index.astype(int)
    for i in to_clip:
        dbo.write(dbi[i][0])
        shpo.write(shpi.get(i))
    shpo.close()
    shpi.close()
    dbo.close()
    dbi.close()
    os.system('cp %s %s'%(shp_in[:-3]+'prj', shp_out[:-3]+'prj'))
    return shp_out

def pip_shps_multi(pt_shp, poly_shp, polyID_col=None, out_shp=None,
        empty='empty'):
    '''
    Point in polygon operation taking as input a point and a polygon
    shapefiles (running on multicore)
    ...

    Arguments
    =========
    pt_shp          : str
                      Path to point shapefile
    poly_shp        : str
                      Path to polygon shapefile
    polyID_col      : str
                      Name of the column in the polygon shapefile to be used as ID
                      in the output shape
    out_shp         : str
                      Path to the output shapefile where to write pt_shp with a
                      column with correspondences appended (Optional, defaults to
                      None)
    empty           : str
                      String to insert if the point is not contained in any
                      polygon. Defaults to 'empty'

    Returns
    =======
    correspondences : list
                      List of length len(pt_shp) with the polygon ID where the
                      points are located
    '''
    t0 = time.time()
    polys = ps.open(poly_shp)
    if polyID_col:
        polyIDs = ps.open(poly_shp[:-3]+'dbf').by_col(polyID_col)
    pl = ps.cg.PolygonLocator(polys)
    t1 = time.time()
    print '\t', t1-t0, ' secs to build rtree'

    pts = ps.open(pt_shp)
    lpts = list(pts)
    parss = [(pt, pl) for pt in lpts]
    cores = mp.cpu_count()
    pool = mp.Pool(cores)
    correspondences = pool.map(_poly4pt, parss)
    t2 = time.time()
    print '\t', t2-t1, ' secs to get correspondences'
    if polyID_col:
        correspondences_names= []
        for i in correspondences:
            try:
                correspondences_names.append(polyIDs[int(i)])
            except:
                correspondences_names.append(empty)
        correspondences = correspondences_names
    pts.close()
    polys.close()
    t3 = time.time()
    print '\t', t3-t2, ' secs to convert correspondences'
    if out_shp:
        _writeShp()
    return correspondences

def pip_xy_shp_multi(xy, poly_shp, polyID_col=None, out_shp=None,
        empty=None):
    '''
    Point in polygon operation taking as input a points array and a polygon
    shapefile (running on multicore)
    ...

    Arguments
    =========
    xy              : np.array
                      nx2 array with xy coordinates
    poly_shp        : str
                      Path to polygon shapefile
    polyID_col      : str
                      Name of the column in the polygon shapefile to be used as ID
                      in the output shape
    out_shp         : str
                      Path to the output shapefile where to write xy with a
                      column with correspondences appended (Optional, defaults to
                      None)
    empty           : str
                      String to insert if the point is not contained in any
                      polygon. Defaults to None

    Returns
    =======
    correspondences : list
                      List of length len(xy) with the polygon ID where the
                      points are located
    '''
    t0 = time.time()
    polys = ps.open(poly_shp)
    if polyID_col:
        polyIDs = ps.open(poly_shp[:-3]+'dbf').by_col(polyID_col)
    pl = ps.cg.PolygonLocator(polys)
    t1 = time.time()
    print '\t', t1-t0, ' secs to build rtree'

    parss = zip(xy, [pl]*xy.shape[0])
    cores = mp.cpu_count()
    pool = mp.Pool(cores)
    correspondences = pool.map(_poly4xy, parss)
    t2 = time.time()
    print '\t', t2-t1, ' secs to get correspondences'
    if polyID_col:
        correspondences_names= []
        for i in correspondences:
            try:
                correspondences_names.append(polyIDs[int(i)])
            except:
                correspondences_names.append(empty)
        correspondences = correspondences_names
    polys.close()
    t3 = time.time()
    print '\t', t3-t2, ' secs to convert correspondences'
    if out_shp:
        _writeShp()
    return correspondences

def _poly4xy(pars):
    'Return the poly where pt is'
    pt, pl = pars
    x, y = pt
    candidates = pl.contains_point(pt)
    for cand in candidates:
        if cand.contains_point(pt)==1:
            return cand.id-1 #one-offset
    return 'out'

def _poly4pt(pars):
    pt, pl = pars
    'Return the poly where pt is'
    x,y = pt
    candidates = pl.contains_point(pt)
    for cand in candidates:
        if cand.contains_point(pt)==1:
            return cand.id-1 #one-offset
    return 'out'

def _writeShp():
    oShp = ps.open(out_shp, 'w')
    shp = ps.open(pt_shp)
    oDbf = ps.open(out_shp[:-3]+'dbf', 'w')
    dbf = ps.open(pt_shp[:-3]+'dbf')
    oDbf.header = dbf.header
    col_name = 'in_poly'
    col_spec = ('C', 14, 0)
    if polyID_col:
        col_name = polyID_col
        #db = ps.open(poly_shp[:-3]+'dbf')
        #col_spec = db.field_spec[db.header.index(polyID_col)]
    oDbf.header.append(col_name)
    oDbf.field_spec = dbf.field_spec
    oDbf.field_spec.append(col_spec)
    for poly, rec, i in zip(shp, dbf, correspondences):
        oShp.write(poly)
        rec.append(i)
        oDbf.write(rec)
    shp.close()
    oShp.close()
    dbf.close()
    oDbf.close()
    prj = open(pt_shp[:-3]+'prj').read()
    oPrj = open(out_shp[:-3]+'prj', 'w')
    oPrj.write(prj); oPrj.close()
    t4 = time.time()
    print '\t', t4-t3, ' seconds to write shapefile'
    print 'Shapefile written to %s'%out_shp

def pip_shps(pt_shp, poly_shp, polyID_col=None, out_shp=None, empty='empty'):
    '''
    Point in polygon operation taking as input a point and a polygon
    shapefiles
    ...

    Arguments
    =========
    pt_shp          : str
                      Path to point shapefile
    poly_shp        : str
                      Path to polygon shapefile
    polyID_col      : str
                      Name of the column in the polygon shapefile to be used as ID
                      in the output shape
    out_shp         : str
                      Path to the output shapefile where to write pt_shp with a
                      column with correspondences appended (Optional, defaults to
                      None)
    empty           : str
                      String to insert if the point is not contained in any
                      polygon. Defaults to 'empty'

    Returns
    =======
    correspondences : list
                      List of length len(pt_shp) with the polygon ID where the
                      points are located
    '''
    def _poly4pt_pd(pt):
        'Return the poly where pt is in pandas'
        x,y = pt
        candidates = bbs[(bbs['left']<x) & (bbs['right']>x) & \
                (bbs['down']<y) & (bbs['up']>y)].index
        for cand in candidates:
            poly_cand = polys.get(cand)
            if poly_cand.contains_point(pt)==1:
                return cand
        return 'out'
    t0 = time.time()
    polys = ps.open(poly_shp)
    id = []
    bbs = {'left': [], 'right': [], 'up': [], 'down': []}
    for c, poly in enumerate(polys):
        id.append(c)
        bb = poly.bounding_box
        bbs['left'].append(bb.left)
        bbs['right'].append(bb.right)
        bbs['up'].append(bb.upper)
        bbs['down'].append(bb.lower)
    if polyID_col:
        polyIDs = ps.open(poly_shp[:-3]+'dbf').by_col(polyID_col)
    bbs = pd.DataFrame(bbs, index=id)
    t1 = time.time()
    print '\t', t1-t0, ' secs to build bbs'

    pts = ps.open(pt_shp)
    lpts = list(pts)
    correspondences = map(_poly4pt_pd, lpts)
    t2 = time.time()
    print '\t', t2-t1, ' secs to get correspondences'
    if polyID_col:
        correspondences_names= []
        for i in correspondences:
            try:
                correspondences_names.append(polyIDs[int(i)])
            except:
                correspondences_names.append(empty)
        correspondences = correspondences_names
    pts.close()
    polys.close()
    t3 = time.time()
    print '\t', t3-t2, ' secs to convert correspondences'
    if out_shp:
        _writeShp()
    return correspondences

def dist_A2B(a, b, metric='euclidean', nearestK=None, multicore=False):
    '''
    Calculate distance from every point in A to every point in B. Really it is
    a memory efficient wrapper for scipy.spatial.cdist with DataFrame support.
    Output is returned in a Series with hierarchical index where the first
    level are observations from A and second is observations from B.

    NOTE: it assumes coordinates in A and B projected
    ...

    Arguments
    ---------
    a           : DataFrame
                  Table with points in group A. Every column is each of the
                  dimensions for the distance to be computed on.
    b           : DataFrame
                  Table with points in group B. Every column is each of the
                  dimensions for the distance to be computed on.
    metric      : str
                  Desired metric to be used to compute the distance. Defaults to
                  'ecuclidean'. See options at
                  http://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance.cdist.html#scipy.spatial.distance.cdist
                  Note that really, the function calculates cdist(i, B) for every
                  i in A.
    nearestK    : int
                  Number of nearest elements in B to keep the distance from A.
                  Defaults to None so all are kept.
    multicore   : boolean
                  Switcher to span processes to multiple cores. Activating it
                  (defaults) speeds up the computation but also uses up more memory

    Returns
    -------
    ab          : Series
                  Table hierarchically indexed of distances. It uses indices
                  provided in A and B
    '''
    if multicore:
        pool = mp.Pool(mp.cpu_count())
        dists = pd.concat(pool.map(_a2B, [(row[1], b, metric, nearestK) for row in a.iterrows()]))
    else:
        dists = pd.concat(map(_a2B, [(row[1], b, metric, nearestK) for row in a.iterrows()]))
    return dists

def _a2B(aBmetricNearestK):
    a, B, metric, nearestK = aBmetricNearestK
    dists = cdist(a.values[None, :], B.values, metric=metric).flatten()
    id = pd.MultiIndex.from_arrays([np.array([a.name]*B.shape[0]), \
            B.index.values])
    s = pd.Series(dists, index=id)
    if nearestK:
        _ = s.sort()
        sk = s[:nearestK]
        del s
        return sk
    else:
        return s

def transCRS(db, prj_link, lat='lat', lon='lon'):
    '''
    Re-project 'lon' and 'lat' columns from WGS84 to prj_link and put it in
    'x' and 'y' columns
    ...

    Arguments
    ---------
    db          : DataFrame
                  DataFrame with coordinates to be reprojected
    prj_link    : str
                  Path to .prj to project lon/lat data
    lat         : str
                  Column name in db for lattitude
    lon         : str
                  Column name in db for longitude
    Returns
    -------
    db          : DataFrame
                  Original DataFrame to which columns 'x' and 'y' have been
                  added with projected coordinates
    '''
    orig = osr.SpatialReference()
    orig.SetWellKnownGeogCS("WGS84")
    target = osr.SpatialReference()
    #See link for this hack
    #http://forum.osgearth.org/Proj4-error-No-translation-for-lambert-conformal-conic-to-PROJ-4-format-is-known-td7579032.html
    wkt = (open(prj_link).read()).replace('Lambert_Conformal_Conic', \
            'Lambert_Conformal_Conic_2SP')
    target.ImportFromWkt(wkt)
    #target.ImportFromWkt(open(prj_link).read()) #original
    trCRS = osr.CoordinateTransformation(orig, target)
    prjd_xys = db[['lon', 'lat']].values.tolist()
    prjd_xys = np.array(trCRS.TransformPoints(prjd_xys))[:, :2]
    db['x'] = prjd_xys[:, 0]
    db['y'] = prjd_xys[:, 1]
    return db

if __name__ == "__main__":
    import time
    shpp = ps.examples.get_path('columbus.shp')
    shp = ps.open(shpp)
    xy = np.random.random((1000000, 2))
    xy[0] = shp[0].centroid
    c = pip_xy_shp_multi(xy, shpp)

