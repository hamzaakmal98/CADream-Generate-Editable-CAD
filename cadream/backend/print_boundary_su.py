import glob
import numpy as np

# Adjust the path as needed for your dataset structure
for npy_path in glob.glob('../../dataset/Input_Sample_1/crops/*/input.npy'):
    arr = np.load(npy_path)
    print(npy_path, 'boundary_sum:', int(arr[4].sum()))