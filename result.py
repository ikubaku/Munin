import logging
from pathlib import Path

from zipfile import ZipFile, BadZipFile

import database
from job import SourceInfo, JobLibraryInfo


class CodePosition:
    def __init__(self, lines, columns):
        self.lines = lines
        self.columns = columns

    @staticmethod
    def deserialize(serialized):
        return CodePosition(serialized['lines'], serialized['columns'])


class CodeSlice:
    def __init__(self, start, end):
        self.start = start
        self.end = end

    @staticmethod
    def deserialize(serialized):
        return CodeSlice(
            CodePosition.deserialize(serialized['start']),
            CodePosition.deserialize(serialized['end']),
        )

    def get_code_from(self, code_string):
        if isinstance(code_string, bytes):
            nl = b'\n'
            res = b''
        else:
            nl = '\n'
            res = ''
        lines = code_string.splitlines()[self.start.lines-1:self.end.lines-1+1]
        res += lines[0][self.start.columns-1:] + nl
        if len(lines) > 2:
            res += nl.join(lines[1:-1]) + nl
        res += lines[-1][:self.end.columns-1+1] + nl
        return res

    def get_nearby_from(self, code_string, width=2):
        if isinstance(code_string, bytes):
            nl = b'\n'
        else:
            nl = '\n'
        lines = code_string.splitlines()
        start_lines = max(1, self.start.lines - width)
        end_lines = min(len(lines), self.end.lines + width)
        res = nl.join(lines[start_lines-1:end_lines-1]) + nl
        return res


class Scores:
    def __init__(self, project_part, example_sketch_part):
        self.project_part = project_part
        self.example_sketch_part = example_sketch_part

    @staticmethod
    def deserialize(serialized):
        return Scores(serialized['project_part'], serialized['example_sketch_part'])


class ClonePair:
    def __init__(self, project, example_sketch, scores):
        self.project = project
        self.example_sketch = example_sketch
        self.scores = scores

    @staticmethod
    def deserialize(serialized):
        return ClonePair(
            CodeSlice.deserialize(serialized['project']),
            CodeSlice.deserialize(serialized['example_sketch']),
            Scores.deserialize(serialized['scores']),
        )


class JobResult:
    def __init__(self, project, example_sketch, job_library_info, clone_pairs):
        self.project = project
        self.example_sketch = example_sketch
        self.job_library_info = job_library_info
        self.clone_pairs = clone_pairs


class ResultConverter:
    JOB_RESULT_FILE_NAME = 'result.txt'
    PAIR_INFO_FILE_NAME = 'pair.txt'
    CLONE_PREFIX = 'clone'
    NEARBY_PREFIX = 'nearby'
    PROJECT_TAG_NAME = 'p'
    EXAMPLE_SKETCH_TAG_NAME = 'e'

    def __init__(self, database_root_path, project_sketch_path):
        # FIXME: Database methods should be implemented and used, instead of inspecting the database with this class.
        self.database_root_path = Path(database_root_path).expanduser()
        self.project_sketch_path = project_sketch_path.expanduser()
        self.results = None

    def load_results_from_serialized(self, serialized):
        results = serialized['results']
        self.results = []
        for r in results:
            project = SourceInfo.deserialize(r['job']['project'])
            example_sketch = SourceInfo.deserialize(r['job']['example_sketch'])
            job_library_info = JobLibraryInfo.deserialize(r['job']['library_info'])
            clone_pairs = []
            if 'clone_pairs' in r:
                for p in r['clone_pairs']:
                    clone_pairs.append(ClonePair.deserialize(p))
            self.results.append(JobResult(project, example_sketch, job_library_info, clone_pairs))

    @staticmethod
    def pretty_print_result_to(filename, job_result):
        data = ['Project source file: {}\n'.format(job_result.project.location),
                'Example sketch source file: {}\n'.format(job_result.example_sketch.location),
                'Library name: {}\n'.format(job_result.job_library_info.name),
                'Library version: {}\n'.format(str(job_result.job_library_info.version)),
                'Found pairs: {}\n'.format(len(job_result.clone_pairs))]
        with open(filename, 'w') as f:
            f.writelines(data)

    def get_project_source_file_content(self, filename):
        with open(self.project_sketch_path.joinpath(filename)) as f:
            return f.read()

    def get_example_sketch_source_file_content(self, archive_path, archive_root_name, example_filename):
        try:
            z = ZipFile(
                self.database_root_path
                    .joinpath(database.Database.LIBRARY_STORAGE_DIRECTORY)
                    .joinpath(archive_path)
            )
        except BadZipFile as ex:
            logging.error('Invalid Zip archive: {}'.format(archive_path))
            logging.error('Description: {}'.format(str(ex.args[0])))
            return
        with z:
            source_filename = '{}/examples/{}'.format(archive_root_name, example_filename)
            return z.read(source_filename)

    @staticmethod
    def extract_clone_pair_to(directory_path, clone_pair, project_source_content, example_sketch_source_content):
        data = ['Project:\n',
                '    at: {}:{}\n'.format(clone_pair.project.start.lines, clone_pair.project.start.columns),
                '    to: {}:{}\n'.format(clone_pair.project.end.lines, clone_pair.project.end.columns),
                '    score: {}\n'.format(clone_pair.scores.project_part),
                '\n',
                'Example sketch:\n',
                '    at: {}:{}\n'.format(clone_pair.example_sketch.start.lines, clone_pair.example_sketch.start.columns),
                '    to: {}:{}\n'.format(clone_pair.example_sketch.end.lines, clone_pair.example_sketch.end.columns),
                '    score: {}\n'.format(clone_pair.scores.example_sketch_part)]
        with open(directory_path.joinpath(ResultConverter.PAIR_INFO_FILE_NAME), 'w') as f:
            f.writelines(data)
        project_clone_code = clone_pair.project.get_code_from(project_source_content)
        project_clone_nearby = clone_pair.project.get_nearby_from(project_source_content)
        example_sketch_clone_code = clone_pair.example_sketch.get_code_from(example_sketch_source_content)
        example_sketch_clone_nearby = clone_pair.example_sketch.get_nearby_from(example_sketch_source_content)
        with open(directory_path.joinpath('{}_{}.txt'.format(
            ResultConverter.CLONE_PREFIX,
            ResultConverter.PROJECT_TAG_NAME
        )), 'w') as f:
            f.write(project_clone_code)
        with open(directory_path.joinpath('{}_{}.txt'.format(
            ResultConverter.NEARBY_PREFIX,
            ResultConverter.PROJECT_TAG_NAME
        )), 'w') as f:
            f.write(project_clone_nearby)
        with open(directory_path.joinpath('{}_{}.txt'.format(
            ResultConverter.CLONE_PREFIX,
            ResultConverter.EXAMPLE_SKETCH_TAG_NAME
        )), 'wb') as f:
            f.write(example_sketch_clone_code)
        with open(directory_path.joinpath('{}_{}.txt'.format(
            ResultConverter.NEARBY_PREFIX,
            ResultConverter.EXAMPLE_SKETCH_TAG_NAME
        )), 'wb') as f:
            f.write(example_sketch_clone_nearby)

    def generate_readable_results(self, output_path):
        output_path = output_path.expanduser()
        if self.results is None:
            raise ValueError('The results are not loaded.')
        if output_path.exists():
            raise ValueError('Destination already exists.')
        output_path.mkdir(0o755)
        n_clone_result = 0
        for r in self.results:
            if len(r.clone_pairs) == 0:
                continue
            clone_result_path = output_path.joinpath('result_{:06}'.format(n_clone_result))
            clone_result_path.mkdir(0o755)
            ResultConverter.pretty_print_result_to(clone_result_path.joinpath(ResultConverter.JOB_RESULT_FILE_NAME), r)
            n_pairs = 0
            for p in r.clone_pairs:
                clone_pair_directory_path = clone_result_path.joinpath('pair_{:06}'.format(n_pairs))
                clone_pair_directory_path.mkdir(0o755)
                project_source_content = self.get_project_source_file_content(r.project.location)
                example_sketch_source_content = self.get_example_sketch_source_file_content(
                    r.job_library_info.location,
                    r.job_library_info.archive_root,
                    r.example_sketch.location
                )
                ResultConverter.extract_clone_pair_to(
                    clone_pair_directory_path,
                    p,
                    project_source_content,
                    example_sketch_source_content
                )
                n_pairs += 1
            n_clone_result += 1
