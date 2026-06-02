from sentence_transformers import SentenceTransformer
import numpy as np

class DependencyMiner:
    """Determines prerequisite similarities between learning concepts."""
    
    def __init__(self, model_name='all-MiniLM-L6-v2', db_client=None):
        print(f"Loading Sentence Transformer model: {model_name}...")
        self.model = SentenceTransformer(model_name)
        self.db = db_client

    def compute_cosine_similarity(self, vec_a, vec_b):
        """Computes Cosine Similarity between two text embeddings."""
        dot_product = np.dot(vec_a, vec_b)
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)

    def determine_prerequisites(self, segments):
        """
        Assesses similarity between segments.
        If Sim > 0.75 and segment i precedes j in time, establish 'IS_PREREQUISITE_FOR'.
        If Sim > 0.85 (strong sequential flow), also establish 'LEADS_TO'.
        """
        print(f"Determining prerequisites across {len(segments)} segments...")

        texts = [seg.get('transcript', '') for seg in segments]
        embeddings = self.model.encode(texts)

        node_query = """
        MATCH (n)-[r]->()
        WHERE r.source_time = $time AND n.name IS NOT NULL
        RETURN n.name AS name, labels(n)[0] AS label
        LIMIT 1
        """

        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                sim = self.compute_cosine_similarity(embeddings[i], embeddings[j])

                if sim >= 0.75:
                    print(f"High Similarity ({sim:.2f}) found between segment {i} and {j}. Creating IS_PREREQUISITE_FOR relationship...")

                    if self.db:
                        start_i = segments[i].get('start_time')
                        start_j = segments[j].get('start_time')

                        nodes_i = self.db.execute_read(node_query, {"time": start_i})
                        nodes_j = self.db.execute_read(node_query, {"time": start_j})

                        if nodes_i and nodes_j:
                            subj = nodes_i[0]['name']
                            subj_label = nodes_i[0]['label'] or 'Entity'
                            obj = nodes_j[0]['name']
                            obj_label = nodes_j[0]['label'] or 'Entity'

                            prereq_query = f"""
                            MATCH (s:`{subj_label}` {{name: $subject}})
                            MATCH (o:`{obj_label}` {{name: $obj}})
                            MERGE (s)-[r:IS_PREREQUISITE_FOR]->(o)
                            ON CREATE SET r.similarity = $sim, r.weight = 1
                            ON MATCH SET r.weight = coalesce(r.weight, 1) + 1
                            """
                            try:
                                self.db.execute_write(prereq_query, {
                                    "subject": subj,
                                    "obj": obj,
                                    "sim": float(sim)
                                })
                                print(f"-> Created: ({subj}) -[IS_PREREQUISITE_FOR]-> ({obj}) [sim={sim:.2f}]")
                            except Exception as e:
                                print(f"-> Failed to create prerequisite relationship: {e}")

                            # Strong sequential flow: also add LEADS_TO
                            if sim >= 0.85:
                                leads_query = f"""
                                MATCH (s:`{subj_label}` {{name: $subject}})
                                MATCH (o:`{obj_label}` {{name: $obj}})
                                MERGE (s)-[r:LEADS_TO]->(o)
                                ON CREATE SET r.similarity = $sim, r.weight = 1
                                ON MATCH SET r.weight = coalesce(r.weight, 1) + 1
                                """
                                try:
                                    self.db.execute_write(leads_query, {
                                        "subject": subj,
                                        "obj": obj,
                                        "sim": float(sim)
                                    })
                                    print(f"-> Created: ({subj}) -[LEADS_TO]-> ({obj}) [sim={sim:.2f}]")
                                except Exception as e:
                                    print(f"-> Failed to create LEADS_TO relationship: {e}")
                        else:
                            print(f"-> No graph entities found for segments {i} (t={start_i}) and/or {j} (t={start_j}). Skipping.")

        return True

    def detect_learning_paths(self, segments):
        """
        Groups consecutive highly-similar segments (sim >= 0.80) into named learning
        path clusters and inserts them as Path nodes with IS_PART_OF edges.
        """
        print(f"Detecting learning path clusters across {len(segments)} segments...")
        if not self.db:
            return

        texts = [seg.get('transcript', '') for seg in segments]
        embeddings = self.model.encode(texts)

        # Build adjacency: consecutive segment pairs above threshold form a chain
        CHAIN_THRESHOLD = 0.80
        chains = []
        current_chain = [0]

        for i in range(len(embeddings) - 1):
            sim = self.compute_cosine_similarity(embeddings[i], embeddings[i + 1])
            if sim >= CHAIN_THRESHOLD:
                current_chain.append(i + 1)
            else:
                if len(current_chain) >= 3:
                    chains.append(list(current_chain))
                current_chain = [i + 1]

        if len(current_chain) >= 3:
            chains.append(list(current_chain))

        node_query = """
        MATCH (n)-[r]->()
        WHERE r.source_time = $time AND n.name IS NOT NULL
        RETURN n.name AS name, labels(n)[0] AS label
        LIMIT 1
        """

        for chain_idx, chain in enumerate(chains):
            path_name = f"Learning Path {chain_idx + 1}"
            print(f"  Path cluster detected: {path_name} (segments {chain[0]}..{chain[-1]})")

            # Create Path node
            create_path_query = "MERGE (p:Path {name: $name})"
            try:
                self.db.execute_write(create_path_query, {"name": path_name})
            except Exception as e:
                print(f"  Could not create path node: {e}")
                continue

            # Link segment nodes to path and add sequential LEADS_TO edges
            prev_node = None
            for order, seg_idx in enumerate(chain):
                start_time = segments[seg_idx].get('start_time')
                nodes = self.db.execute_read(node_query, {"time": start_time})
                if not nodes:
                    continue

                node_name = nodes[0]['name']
                node_label = nodes[0]['label'] or 'Entity'

                # IS_PART_OF -> Path
                part_query = f"""
                MATCH (n:`{node_label}` {{name: $name}})
                MATCH (p:Path {{name: $path}})
                MERGE (n)-[r:IS_PART_OF]->(p)
                ON CREATE SET r.order = $order
                """
                try:
                    self.db.execute_write(part_query, {
                        "name": node_name, "path": path_name, "order": order
                    })
                    print(f"    ({node_name}) -[IS_PART_OF]-> ({path_name}) [order={order}]")
                except Exception as e:
                    print(f"    Failed IS_PART_OF for '{node_name}': {e}")

                # LEADS_TO chain within path
                if prev_node:
                    prev_name, prev_label = prev_node
                    leads_query = f"""
                    MATCH (s:`{prev_label}` {{name: $subject}})
                    MATCH (o:`{node_label}` {{name: $obj}})
                    MERGE (s)-[r:LEADS_TO]->(o)
                    ON CREATE SET r.path = $path, r.weight = 1
                    ON MATCH SET r.weight = coalesce(r.weight, 1) + 1
                    """
                    try:
                        self.db.execute_write(leads_query, {
                            "subject": prev_name, "obj": node_name, "path": path_name
                        })
                        print(f"    ({prev_name}) -[LEADS_TO]-> ({node_name})")
                    except Exception as e:
                        print(f"    Failed LEADS_TO for '{prev_name}' -> '{node_name}': {e}")

                prev_node = (node_name, node_label)

        print(f"Path detection complete. Found {len(chains)} learning path cluster(s).")
