from app.utils.file_utils import save_uploaded_file

class DummyFile:
    def read(self):
        return b"Test PDF content"

file_path = save_uploaded_file(DummyFile(), "sample.pdf")
print("Saved at:", file_path)
