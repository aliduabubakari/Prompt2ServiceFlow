"""Disposable, network-isolated PostgreSQL transport; no business oracle."""
from __future__ import annotations

import json
import re
import subprocess
import time
import uuid


class DatabaseError(RuntimeError):
    def __init__(self, message):
        super().__init__(message)
        found = re.search(r'ERROR:\s+([0-9A-Z]{5}):', message)
        self.sqlstate = found.group(1) if found else None


def docker(*args, input=None, timeout=60):
    result = subprocess.run(['docker', *args], input=input, text=True, capture_output=True, timeout=timeout)
    if result.returncode: raise DatabaseError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def image_info(image):
    try: info = json.loads(docker('image', 'inspect', image))[0]
    except DatabaseError as exc:
        raise ValueError('PostgreSQL image is not available locally. Run docker pull postgres:16 first. ' + str(exc)) from exc
    return {'requested': image, 'id': info['Id'], 'repo_digests': info.get('RepoDigests') or [],
            'architecture': info['Architecture'], 'os': info['Os']}


class Postgres:
    """All clients run through docker exec over the container's Unix socket."""
    def __init__(self, image):
        self.image = image
        self.name = 'p2sf-csv-controls-' + uuid.uuid4().hex[:12]
        self.started = False

    def __enter__(self):
        try:
            docker('run', '--detach', '--rm', '--name', self.name, '--network', 'none',
                   '--memory', '512m', '--cpus', '1', '--pids-limit', '256',
                   '--tmpfs', '/var/lib/postgresql/data:rw,size=268435456',
                   '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', '-e', 'POSTGRES_DB=p2sf_controls',
                   self.image['id'])
            self.started = True
            deadline = time.monotonic() + 90
            while True:
                result = subprocess.run(['docker', 'exec', self.name, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres', '-d', 'p2sf_controls'],
                    capture_output=True, text=True, timeout=10)
                if result.returncode == 0: break
                if time.monotonic() >= deadline: raise DatabaseError('Local PostgreSQL did not become ready')
                time.sleep(.25)
            self.server_version = self.scalar("SELECT current_setting('server_version_num')::int")
            if not 160000 <= self.server_version < 170000: raise ValueError('This control design requires PostgreSQL major version 16')
            return self
        except BaseException:
            self.close(); raise

    def sql(self, statement):
        return docker('exec', '-i', self.name, 'psql', '-X', '-qAt', '-U', 'postgres', '-d', 'p2sf_controls',
                      '-v', 'ON_ERROR_STOP=1', '-v', 'VERBOSITY=verbose', input=statement, timeout=45)

    def scalar(self, statement): return json.loads(self.sql(statement))

    def close(self):
        if self.started:
            try: docker('rm', '--force', self.name, timeout=30)
            finally: self.started = False

    def __exit__(self, *args): self.close()
