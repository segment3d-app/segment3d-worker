FROM nvcr.io/nvidia/pytorch:21.11-py3

WORKDIR /usr/src/app

COPY . .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install ./gaussian-splatting/submodules/diff-gaussian-rasterization
RUN pip install ./gaussian-splatting/submodules/simple-knn

CMD ["python", "main.py"]
