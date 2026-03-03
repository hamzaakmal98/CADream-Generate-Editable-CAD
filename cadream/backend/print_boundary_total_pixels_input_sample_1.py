import glob
import numpy as np

# Print the sum of the boundary channel for all validation crops of Input_Sample_1
for npy_path in glob.glob('../../dataset/Input_Sample_1/crops/*/input.npy'):
    arr = np.load(npy_path)
    print(npy_path, 'boundary_total_pixels:', int(arr[4].sum()))
