"""Safety contract for the opt-in Lavida candidate build."""
import pathlib
import unittest


class CandidateWorkflowTests(unittest.TestCase):
    def test_build_is_opt_in_and_does_not_publish_stable_aliases(self):
        path = pathlib.Path('.github/workflows/lavida-build.yml')
        self.assertTrue(path.is_file(), 'Candidate build workflow is missing')
        workflow = path.read_text()
        self.assertIn('workflow_dispatch:', workflow)
        self.assertNotIn('\n  push:', workflow)
        self.assertIn('persist-credentials: false', workflow)
        self.assertIn('candidate-${{ github.sha }}', workflow)
        self.assertIn('org.opencontainers.image.revision=${{ github.sha }}', workflow)
        self.assertIn('platforms: linux/amd64,linux/arm64', workflow)
        self.assertIn('docker buildx imagetools inspect', workflow)
        self.assertIn('Refusing to overwrite existing candidate', workflow)
        self.assertNotIn(':latest', workflow)
        self.assertNotIn(':3.3.4-lavida.1', workflow)


if __name__ == '__main__':
    unittest.main()
