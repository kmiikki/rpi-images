"""Compatibility checks by default; exact historical versions only with --snapshot."""
import argparse
import importlib
import importlib.metadata as md
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--contract', type=Path, default=Path(__file__).resolve().parents[1]/'config/lab314/packages.json')
parser.add_argument('--snapshot', action='store_true')
parser.add_argument('--prefix', type=Path, required=True)
parser.add_argument('--functional', action='store_true')
args = parser.parse_args()
contract = json.loads(args.contract.read_text()) if args.snapshot else None
errors = []
if Path(sys.prefix).resolve() != args.prefix.resolve():
    errors.append(f'prefix {sys.prefix} != {args.prefix}')
if errors:sys.exit('\n'.join(errors))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from lab314_policy import version_errors, policy
versions={d.metadata['Name']:d.version for d in md.distributions()}
if args.snapshot:
    # Keep --contract support for exact snapshot diagnostics.
    if platform.python_version()!=contract['python']:errors.append('Snapshot Python version differs')
    for name,expected in contract['packages'].items():
        try:found=md.version(name)
        except md.PackageNotFoundError:found='MISSING'
        if found!=expected:errors.append(name+': snapshot version differs: '+found)
else:
    try:errors.extend(version_errors(versions,platform.python_version()))
    except ValueError as exc:errors.append(str(exc))
    for module in policy()['pip'].values():
        try:importlib.import_module(module)
        except Exception as exc:errors.append(module+': '+str(exc))
    if not errors:
        cv=importlib.import_module('cv2')
        gui=re.search(r'GUI:\s*(\S+)',cv.getBuildInformation())
        if not gui or gui[1].upper() in ('NONE','NO'):
            errors.append('OpenCV must provide a graphical Linux backend')
if '/usr/lib/python3/dist-packages' in sys.path:
    errors.append('Debian dist-packages leaks into lab314')
for font in ('DejaVuSans.ttf', 'DejaVuSans-Bold.ttf'):
    path = Path(sys.prefix)/'lib/python3.14/site-packages/cv2/qt/fonts'/font
    if not path.is_file():
        errors.append('missing Qt font '+str(path))
if errors:
    sys.exit('\n'.join(errors))
subprocess.run([sys.executable, '-B', '-m', 'pip', 'check'], check=True)
print('PASS', 'exact snapshot' if args.snapshot else 'compatible requirements', 'Python, prefix, isolation')
if not args.functional:
    sys.exit(0)

# Small deterministic workloads. Temporary output follows the caller's TMPDIR.
with tempfile.TemporaryDirectory(prefix='lab314-check-') as tmp:
    root = Path(tmp)
    import numpy as np
    import scipy.linalg as la
    import pandas as pd
    import sympy
    import statsmodels.api as sm
    from sklearn.linear_model import LinearRegression
    from numba import njit
    from uncertainties import ufloat
    from pint import UnitRegistry
    from shapely.geometry import Point, LineString, Polygon, MultiPolygon
    import shapely
    import cv2
    import skimage.filters
    from PIL import Image
    import imageio.v3 as iio
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import seaborn
    import xarray as xr
    import netCDF4
    import h5py
    import pyarrow as pa
    import pyarrow.parquet as pq
    import tifffile
    import openpyxl
    import xlsxwriter
    import IPython, ipykernel, spyder_kernels, jupyterlab
    import tqdm, serial
    import rtree, gmpy2, formulaic, exifread, networkx
    import imageio_ffmpeg

    assert np.allclose(la.solve([[2., 0], [0, 4]], [4., 8.]), [2, 2])
    x = np.arange(6.).reshape(-1, 1)
    y = x[:, 0]*2+1
    assert np.allclose(LinearRegression().fit(x, y).predict(x), y)
    assert np.allclose(sm.OLS(y, sm.add_constant(x)).fit().params, [1, 2])
    assert njit(lambda a: a.sum())(np.arange(10)) == 45
    assert sympy.integrate(sympy.Symbol('x'), (sympy.Symbol('x'), 0, 2)) == 2
    assert (ufloat(2, .1)*2).nominal_value == 4
    assert (2*UnitRegistry().meter).to('cm').magnitude == 200
    p = Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])
    q = Polygon([(1, 0), (3, 0), (3, 2), (1, 2)])
    assert p.area == 4 and p.intersection(q).area == 2 and p.union(q).area == 6
    assert Point(1, 1).within(p) and LineString([(0, 0), (2, 0)]).length == 2
    assert MultiPolygon([p, Polygon([(4, 0), (5, 0), (5, 1), (4, 1)])]).area == 5
    assert np.array_equal(shapely.area(np.array([p, q], dtype=object)), [4, 4])
    assert shapely.geos_version_string
    print('PASS Shapely Point/LineString/Polygon/MultiPolygon/intersection/union/area/NumPy GEOS',
          shapely.geos_version_string)
    im = np.zeros((48, 64, 3), np.uint8)
    im[:, :32] = (24, 100, 180)
    for suffix in ('png', 'jpg'):
        filename = str(root/('image.'+suffix))
        assert cv2.imwrite(filename, im)
        assert cv2.imread(filename).shape == im.shape
    assert cv2.getBuildInformation()  # Distribution identity is checked above.
    if args.snapshot:assert cv2.__version__==contract['opencv']
    assert skimage.filters.sobel(im[:, :, 0]).shape == (48, 64)
    assert cv2.contourArea(np.array(p.exterior.coords[:-1], dtype=np.float32)) == p.area
    for codec in ('FFV1', 'MJPG'):
        filename = str(root/(codec+'.avi'))
        writer = cv2.VideoWriter(filename, cv2.CAP_FFMPEG, cv2.VideoWriter_fourcc(*codec), 10, (64, 48))
        assert writer.isOpened()
        for _ in range(5):
            writer.write(im)
        writer.release()
        cap = cv2.VideoCapture(filename)
        for _ in range(5):
            ok, frame = cap.read()
            assert ok and frame.shape == im.shape
            if codec == 'FFV1':
                assert np.array_equal(frame, im)
        assert not cap.read()[0]
        cap.release()
    tifffile.imwrite(root/'im.tif', im)
    assert np.array_equal(iio.imread(root/'im.tif'), im)
    plt.plot([1, 2])
    plt.savefig(root/'plot.png')
    plt.close()
    assert Image.open(root/'plot.png').size[0] > 0
    with h5py.File(root/'a.h5', 'w') as h:
        h['im'] = im
        assert np.array_equal(h['im'][:], im)
    frame = pd.DataFrame({'value': [1, 2]})
    pq.write_table(pa.Table.from_pandas(frame), root/'a.parquet')
    assert pq.read_table(root/'a.parquet').to_pandas().equals(frame)
    array = xr.DataArray([1., 2.], dims=['x'])
    array.to_netcdf(root/'a.nc')
    with xr.open_dataarray(root/'a.nc') as loaded:
        assert loaded.equals(array)
    book = xlsxwriter.Workbook(root/'a.xlsx')
    sheet = book.add_worksheet()
    sheet.write(0, 0, 42)
    book.close()
    assert openpyxl.load_workbook(root/'a.xlsx').active['A1'].value == 42
    assert gmpy2.is_prime(17)
    idx = rtree.index.Index()
    idx.insert(1, (0, 0, 1, 1))
    assert list(idx.intersection((0, 0, 1, 1))) == [1]
    assert formulaic.model_matrix('value', frame).shape[0] == 2
    assert networkx.shortest_path(networkx.path_graph(3), 0, 2) == [0, 1, 2]
    print('PASS scientific calculations, Numba JIT, files, image/video and measurement data')
