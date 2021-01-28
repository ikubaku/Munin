from pathlib import Path
import shutil

import toml


class Session:
    def __init__(self, project_path, jobs_path):
        self.project_path = project_path
        self.jobs_path = jobs_path

    def serialize(self):
        return {
            'project_path': self.project_path,
            'jobs_path': self.jobs_path,
        }

    @staticmethod
    def deserialize(serialized):
        return Session(serialized['project_path'], serialized['jobs_path'])


class SourceInfo:
    def __init__(self, location):
        self.location = location

    def serialize(self):
        return {
            'location': self.location,
        }

    @staticmethod
    def deserialize(serialized):
        return SourceInfo(serialized['location'])


class JobLibraryInfo:
    def __init__(self, name, version, location, archive_root):
        self.name = name
        self.version = version
        self.location = location
        self.archive_root = archive_root

    def serialize(self):
        return {
            'name': self.name,
            'version': self.version,
            'location': self.location,
            'archive_root': self.archive_root,
        }

    @staticmethod
    def deserialize(serialized):
        return JobLibraryInfo(
            serialized['name'],
            serialized['version'],
            serialized['location'],
            serialized['archive_root']
        )

    def from_library_info(self, library_info, archive_root):
        raise NotImplementedError


class Job:
    def __init__(self, project, example_sketch, job_library_info):
        self.project = project
        self.example_sketch = example_sketch
        self.job_library_info = job_library_info

    def serialize(self):
        return {
            'project': self.project.serialize(),
            'example_sketch': self.example_sketch.serialize(),
            'library_info': self.job_library_info.serialize(),
        }

    @staticmethod
    def deserialize(serialized):
        return Job(
            SourceInfo.deserialize(serialized['project']),
            SourceInfo.deserialize(serialized['example_sketch']),
            JobLibraryInfo.deserialize(serialized['library_info']),
        )


class HuginSession:
    HUGIN_JOBS_PATH = 'jobs'
    SESSION_FILE_NAME = 'session.toml'
    JOB_FILE_PREFIX = 'job_'

    def __init__(self, output_path):
        self.session = None
        self.jobs = []
        self.output_path = Path(output_path).expanduser()
        self.project_root = None

    def set_project_root(self, project_root):
        """Set the project root path"""
        self.project_root = Path(project_root).expanduser()

    def create_new_job(
            self,
            project_source_path,
            example_source_path,
            library_name,
            library_version,
            archive_path,
            archive_root
    ):
        """Create and add a new job to the session"""
        job_library_info = JobLibraryInfo(library_name, library_version, archive_path, archive_root)
        job = Job(project_source_path, example_source_path, job_library_info)
        self.jobs.append(job)

    def write(self):
        """Generate the Hugin session"""
        if self.project_root is None:
            raise ValueError("The project root path is not specified.")
        if self.session is None:
            raise ValueError("Tried to generate the session without any valid data.")

        self.secure_directories()
        with open(self.output_path.joinpath(HuginSession.SESSION_FILE_NAME, 'w')) as f:
            toml_string = toml.dumps(self.session.serialize())
            f.write(toml_string)
        shutil.copytree(self.project_root, self.output_path)
        for (i, j) in enumerate(self.jobs):
            file_name = HuginSession.JOB_FILE_PREFIX + str(i) + '.toml'
            with open(file_name, 'w') as f:
                toml_string = toml.dumps(j.serialize())
                f.write(toml_string)

    def secure_directories(self):
        """Create the basic session directory structure to the destination"""
        # expect the directory is not present
        if self.output_path.exists():
            raise ValueError("The destination directory already exists.")
        self.output_path.mkdir(0o755)
        self.output_path.joinpath(HuginSession.HUGIN_JOBS_PATH).mkdir(0o755)
