"""Unpack downloaded ADNI archives into the local Data/Raw layout.

Place ADNI zip files directly in Data/. The script creates folders, extracts
archives, and deletes each zip after successful extraction unless --keep-archives is used.
"""

from __future__ import annotations

import argparse
import shutil
import tarfile
import zipfile
from pathlib import Path


def EnsureDirectory(DirectoryPath: Path) -> None:
    DirectoryPath.mkdir(parents=True, exist_ok=True)


def CreateExpectedDirectoryStructure(DataRootDirectory: Path) -> None:
    """Create the expected raw clinical and imaging directory structure."""
    ExpectedDirectories = [
        DataRootDirectory / "Raw" / "Clinical",
        DataRootDirectory / "Raw" / "Clinical" / "StudyData",
        DataRootDirectory / "Raw" / "Imaging" / "Baseline3T1MPRAGE",
        DataRootDirectory / "Raw" / "Imaging" / "Baseline3T1MPRAGE" / "Manifest",
        DataRootDirectory / "Raw" / "Imaging" / "Baseline3T1MPRAGE" / "Archives",
        DataRootDirectory / "Raw" / "Imaging" / "Baseline3T1MPRAGE" / "Images",
    ]

    for ExpectedDirectory in ExpectedDirectories:
        EnsureDirectory(ExpectedDirectory)


def MoveArchiveFile(SourceFilePath: Path, DestinationFilePath: Path) -> Path:
    """Move an archive into its target raw-data location, replacing an older archive if present."""
    EnsureDirectory(DestinationFilePath.parent)

    if not SourceFilePath.exists():
        raise FileNotFoundError(f"Source file does not exist: {SourceFilePath}")

    if SourceFilePath.resolve() == DestinationFilePath.resolve():
        return DestinationFilePath

    if DestinationFilePath.exists():
        if DestinationFilePath.is_file():
            print(f"Replacing existing archive: {DestinationFilePath}")
            DestinationFilePath.unlink()
        else:
            raise IsADirectoryError(f"Expected file destination, found directory: {DestinationFilePath}")

    print(f"Moving: {SourceFilePath} -> {DestinationFilePath}")
    shutil.move(str(SourceFilePath), str(DestinationFilePath))

    return DestinationFilePath


def ValidateZipMemberPath(ZipMemberName: str) -> None:
    """Reject unsafe paths inside zip archives before extraction."""
    ZipMemberPath = Path(ZipMemberName)

    if ZipMemberPath.is_absolute() or ".." in ZipMemberPath.parts:
        raise RuntimeError(f"Unsafe path in ZIP archive: {ZipMemberName}")


def ValidateTarMemberPath(TarMemberName: str) -> None:
    """Reject unsafe paths inside tar archives before extraction."""
    TarMemberPath = Path(TarMemberName)

    if TarMemberPath.is_absolute() or ".." in TarMemberPath.parts:
        raise RuntimeError(f"Unsafe path in TAR archive: {TarMemberName}")


def ExtractZipFile(ZipFilePath: Path, DestinationDirectory: Path, DeleteAfterExtraction: bool) -> None:
    """Extract a zip archive and optionally delete it after successful extraction."""
    EnsureDirectory(DestinationDirectory)

    print(f"Extracting ZIP: {ZipFilePath}")

    with zipfile.ZipFile(ZipFilePath, "r") as ZipArchive:
        for ZipMemberName in ZipArchive.namelist():
            ValidateZipMemberPath(ZipMemberName)

        ZipArchive.extractall(DestinationDirectory)

    if DeleteAfterExtraction:
        print(f"Deleting ZIP: {ZipFilePath}")
        ZipFilePath.unlink()


def ExtractTarGzFile(TarGzFilePath: Path, DestinationDirectory: Path, DeleteAfterExtraction: bool) -> None:
    """Extract a tar.gz archive and optionally delete it after successful extraction."""
    EnsureDirectory(DestinationDirectory)

    print(f"Extracting TAR.GZ: {TarGzFilePath}")

    with tarfile.open(TarGzFilePath, "r:gz") as TarArchive:
        for TarMember in TarArchive.getmembers():
            ValidateTarMemberPath(TarMember.name)

        TarArchive.extractall(DestinationDirectory)

    if DeleteAfterExtraction:
        print(f"Deleting TAR.GZ: {TarGzFilePath}")
        TarGzFilePath.unlink()


def RemoveDuplicatePaths(FilePaths: list[Path]) -> list[Path]:
    """Return paths with duplicates removed after resolving absolute paths."""
    SeenResolvedPaths: set[Path] = set()
    UniqueFilePaths: list[Path] = []

    for FilePath in FilePaths:
        ResolvedFilePath = FilePath.resolve()

        if ResolvedFilePath in SeenResolvedPaths:
            continue

        SeenResolvedPaths.add(ResolvedFilePath)
        UniqueFilePaths.append(FilePath)

    return UniqueFilePaths


def FindClinicalDownloadZip(DataRootDirectory: Path) -> Path | None:
    """Find the ADNI clinical study-data zip in Data/ or its raw destination."""
    CandidatePaths = [
        DataRootDirectory / "download.zip",
        DataRootDirectory / "ADNI_StudyData.zip",
        DataRootDirectory / "Raw" / "Clinical" / "ADNI_StudyData.zip",
    ]

    for CandidatePath in CandidatePaths:
        if CandidatePath.exists():
            return CandidatePath

    return None


def FindImagingMetadataZipFiles(DataRootDirectory: Path) -> list[Path]:
    """Find IDA metadata zip files in Data/ or the imaging manifest folder."""
    CandidateDirectories = [
        DataRootDirectory,
        DataRootDirectory / "Raw" / "Imaging" / "Baseline3T1MPRAGE" / "Manifest",
    ]

    MetadataZipFiles: list[Path] = []

    for CandidateDirectory in CandidateDirectories:
        if not CandidateDirectory.exists():
            continue

        for ZipFilePath in sorted(CandidateDirectory.glob("*.zip")):
            if "metadata" in ZipFilePath.name.lower():
                MetadataZipFiles.append(ZipFilePath)

    return RemoveDuplicatePaths(MetadataZipFiles)


def FindImagingArchiveZipFiles(DataRootDirectory: Path) -> list[Path]:
    """Find MRI image archive zips in Data/ or the imaging archives folder."""
    CandidateDirectories = [
        DataRootDirectory,
        DataRootDirectory / "Raw" / "Imaging" / "Baseline3T1MPRAGE" / "Archives",
    ]

    ImageZipFiles: list[Path] = []

    for CandidateDirectory in CandidateDirectories:
        if not CandidateDirectory.exists():
            continue

        for ZipFilePath in sorted(CandidateDirectory.glob("ADNI_Baseline_3T_T1_MPRAG*.zip")):
            if "metadata" not in ZipFilePath.name.lower():
                ImageZipFiles.append(ZipFilePath)

    return RemoveDuplicatePaths(ImageZipFiles)


def PrepareClinicalRawData(DataRootDirectory: Path, DeleteArchives: bool) -> None:
    """Move and extract the ADNI clinical archive and nested clinical archives."""
    ClinicalRootDirectory = DataRootDirectory / "Raw" / "Clinical"
    StudyDataDirectory = ClinicalRootDirectory / "StudyData"

    ClinicalDownloadZipFile = FindClinicalDownloadZip(DataRootDirectory)

    if ClinicalDownloadZipFile is None:
        print("No clinical study-data zip found.")
        print(f"Expected: {DataRootDirectory / 'download.zip'}")
        return

    DestinationClinicalZipFile = ClinicalRootDirectory / "ADNI_StudyData.zip"

    ClinicalDownloadZipFile = MoveArchiveFile(
        SourceFilePath=ClinicalDownloadZipFile,
        DestinationFilePath=DestinationClinicalZipFile,
    )

    ExtractZipFile(
        ZipFilePath=ClinicalDownloadZipFile,
        DestinationDirectory=StudyDataDirectory,
        DeleteAfterExtraction=DeleteArchives,
    )

    AdniMergeArchiveFiles = sorted(StudyDataDirectory.glob("ADNIMERGE2*.tar.gz"))

    for AdniMergeArchiveFile in AdniMergeArchiveFiles:
        ExtractTarGzFile(
            TarGzFilePath=AdniMergeArchiveFile,
            DestinationDirectory=StudyDataDirectory,
            DeleteAfterExtraction=False,
        )

    StandardisedListZipFiles = sorted(StudyDataDirectory.glob("ADNI_3T_MRI_Standardized_Lists*.zip"))

    for StandardisedListZipFile in StandardisedListZipFiles:
        StandardisedListDirectory = StudyDataDirectory / "ADNI_3T_MRI_Standardized_Lists"

        ExtractZipFile(
            ZipFilePath=StandardisedListZipFile,
            DestinationDirectory=StandardisedListDirectory,
            DeleteAfterExtraction=False,
        )


def PrepareImagingRawData(DataRootDirectory: Path, DeleteArchives: bool) -> None:
    """Move and extract IDA metadata and MRI image archives."""
    ImagingRootDirectory = DataRootDirectory / "Raw" / "Imaging" / "Baseline3T1MPRAGE"
    ManifestDirectory = ImagingRootDirectory / "Manifest"
    ArchivesDirectory = ImagingRootDirectory / "Archives"
    ImagesDirectory = ImagingRootDirectory / "Images"

    MetadataZipFiles = FindImagingMetadataZipFiles(DataRootDirectory)
    ImageZipFiles = FindImagingArchiveZipFiles(DataRootDirectory)

    if not MetadataZipFiles:
        print("No IDA metadata zip found.")

    for MetadataZipFile in MetadataZipFiles:
        DestinationMetadataZipFile = ManifestDirectory / MetadataZipFile.name

        MetadataZipFile = MoveArchiveFile(
            SourceFilePath=MetadataZipFile,
            DestinationFilePath=DestinationMetadataZipFile,
        )

        MetadataExtractionDirectory = ManifestDirectory / MetadataZipFile.stem

        ExtractZipFile(
            ZipFilePath=MetadataZipFile,
            DestinationDirectory=MetadataExtractionDirectory,
            DeleteAfterExtraction=DeleteArchives,
        )

    if not ImageZipFiles:
        print("No MRI image archive zips found.")

    for ImageZipFile in ImageZipFiles:
        DestinationImageZipFile = ArchivesDirectory / ImageZipFile.name

        ImageZipFile = MoveArchiveFile(
            SourceFilePath=ImageZipFile,
            DestinationFilePath=DestinationImageZipFile,
        )

        ExtractZipFile(
            ZipFilePath=ImageZipFile,
            DestinationDirectory=ImagesDirectory,
            DeleteAfterExtraction=DeleteArchives,
        )


def CountFiles(DirectoryPath: Path) -> int:
    if not DirectoryPath.exists():
        return 0

    return sum(1 for FilePath in DirectoryPath.rglob("*") if FilePath.is_file())


def CountNiftiFiles(DirectoryPath: Path) -> int:
    """Count extracted NIfTI files, including .nii and .nii.gz files."""
    if not DirectoryPath.exists():
        return 0

    NiftiFileCount = 0

    for FilePath in DirectoryPath.rglob("*"):
        if not FilePath.is_file():
            continue

        if FilePath.name.endswith(".nii") or FilePath.name.endswith(".nii.gz"):
            NiftiFileCount += 1

    return NiftiFileCount


def CountPreparedFiles(DataRootDirectory: Path) -> None:
    """Print a short summary of unpacked clinical, manifest, archive, and image files."""
    ClinicalStudyDataDirectory = DataRootDirectory / "Raw" / "Clinical" / "StudyData"
    ImagingManifestDirectory = DataRootDirectory / "Raw" / "Imaging" / "Baseline3T1MPRAGE" / "Manifest"
    ImagingArchivesDirectory = DataRootDirectory / "Raw" / "Imaging" / "Baseline3T1MPRAGE" / "Archives"
    ImagingImagesDirectory = DataRootDirectory / "Raw" / "Imaging" / "Baseline3T1MPRAGE" / "Images"

    ClinicalFileCount = CountFiles(ClinicalStudyDataDirectory)
    ManifestFileCount = CountFiles(ImagingManifestDirectory)
    RemainingArchiveFileCount = CountFiles(ImagingArchivesDirectory)
    ExtractedImageFileCount = CountFiles(ImagingImagesDirectory)
    NiftiFileCount = CountNiftiFiles(ImagingImagesDirectory)

    print()
    print("Summary")
    print("-------")
    print(f"Clinical files: {ClinicalFileCount}")
    print(f"Manifest files: {ManifestFileCount}")
    print(f"Remaining archive files: {RemainingArchiveFileCount}")
    print(f"Extracted image files: {ExtractedImageFileCount}")
    print(f"Extracted NIfTI files: {NiftiFileCount}")


def ParseArguments() -> argparse.Namespace:
    """Parse command-line arguments for unpacking raw data."""
    ArgumentParser = argparse.ArgumentParser(
        description="Unpack locally downloaded ADNI archives into the expected Data/Raw layout."
    )

    ArgumentParser.add_argument(
        "--data-root",
        type=Path,
        default=Path("Data"),
        help="Path to the repository Data directory. Default: Data",
    )

    ArgumentParser.add_argument(
        "--keep-archives",
        action="store_true",
        help="Keep ZIP archives after successful extraction. By default, archives are deleted after extraction.",
    )

    ArgumentParser.add_argument(
        "--clinical-only",
        action="store_true",
        help="Only unpack clinical downloads.",
    )

    ArgumentParser.add_argument(
        "--imaging-only",
        action="store_true",
        help="Only unpack imaging downloads.",
    )

    return ArgumentParser.parse_args()


def Main() -> None:
    Arguments = ParseArguments()

    if Arguments.clinical_only and Arguments.imaging_only:
        raise ValueError("Use either --clinical-only or --imaging-only, not both.")

    CreateExpectedDirectoryStructure(DataRootDirectory=Arguments.data_root)

    DeleteArchives = not Arguments.keep_archives

    if not Arguments.imaging_only:
        PrepareClinicalRawData(
            DataRootDirectory=Arguments.data_root,
            DeleteArchives=DeleteArchives,
        )

    if not Arguments.clinical_only:
        PrepareImagingRawData(
            DataRootDirectory=Arguments.data_root,
            DeleteArchives=DeleteArchives,
        )

    CountPreparedFiles(DataRootDirectory=Arguments.data_root)


if __name__ == "__main__":
    Main()